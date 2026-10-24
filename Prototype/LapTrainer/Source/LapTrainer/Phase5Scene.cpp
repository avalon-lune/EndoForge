#include "TrainingScene.h"
#include "SimulationBridge.h"
#include "Camera/CameraComponent.h"
#include "Components/SpotLightComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/SceneCaptureComponent2D.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/TextureRenderTarget2D.h"
#include "Engine/Texture2D.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/PlayerInput.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "ImageUtils.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformProcess.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Misc/SecureHash.h"
#include "Misc/EngineVersion.h"
#include "Components/LightComponent.h"
#include "Misc/FileHelper.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "ProceduralMeshComponent.h"
#include "RenderingThread.h"

namespace
{
TSharedPtr<FJsonValue> A5V(const FVector& P)
{ return MakeShared<FJsonValueArray>(TArray<TSharedPtr<FJsonValue>>{MakeShared<FJsonValueNumber>(P.X),MakeShared<FJsonValueNumber>(P.Y),MakeShared<FJsonValueNumber>(P.Z)}); }
FVector A5Read(const TSharedPtr<FJsonValue>& V,double Scale=1)
{ const auto& A=V->AsArray(); return A.Num()==3?FVector(A[0]->AsNumber(),A[1]->AsNumber(),A[2]->AsNumber())*Scale:FVector::ZeroVector; }
bool A5FiniteVector(const TSharedPtr<FJsonObject>& Object,const TCHAR* Key,FVector& Out,double Scale=1)
{
    const TArray<TSharedPtr<FJsonValue>>* Values=nullptr;
    if(!Object.IsValid() || !Object->TryGetArrayField(Key,Values) || Values->Num()!=3) return false;
    for(int32 I=0;I<3;++I)
    {
        double Value=0;
        if(!(*Values)[I]->TryGetNumber(Value) || !FMath::IsFinite(Value)) return false;
        Out[I]=Value*Scale;
    }
    return !Out.ContainsNaN();
}
FString A5Text(const TSharedRef<FJsonObject>& O)
{ FString S; FJsonSerializer::Serialize(O,TJsonWriterFactory<TCHAR,TCondensedJsonPrintPolicy<TCHAR>>::Create(&S)); return S; }
bool A5Save(const FString& Path,const TSharedRef<FJsonObject>& O)
{ return FFileHelper::SaveStringToFile(A5Text(O),*Path,FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM); }
void A5Tangents(FTrainingRenderMesh& M)
{
    TArray<FVector> U,V;U.Init(FVector::ZeroVector,M.Positions.Num());V=U;
    for(int I=0;I+2<M.Triangles.Num();I+=3){int A=M.Triangles[I],B=M.Triangles[I+1],C=M.Triangles[I+2];const FVector E1=M.Positions[B]-M.Positions[A],E2=M.Positions[C]-M.Positions[A];const FVector2D T1=M.UV[B]-M.UV[A],T2=M.UV[C]-M.UV[A];double D=T1.X*T2.Y-T1.Y*T2.X;if(FMath::Abs(D)<1e-12)continue;FVector X=(E1*T2.Y-E2*T1.Y)/D,Y=(E2*T1.X-E1*T2.X)/D;for(int N:{A,B,C}){U[N]+=X;V[N]+=Y;}}
    M.Tangents.SetNum(M.Positions.Num());for(int I=0;I<M.Positions.Num();++I){FVector X=(U[I]-M.Normals[I]*FVector::DotProduct(M.Normals[I],U[I])).GetSafeNormal();if(X.IsNearlyZero())X=FVector::CrossProduct(M.Normals[I],FVector::RightVector).GetSafeNormal();M.Tangents[I]=FProcMeshTangent(X,FVector::DotProduct(FVector::CrossProduct(M.Normals[I],X),V[I])<0);}
}
void A5Normals(FTrainingRenderMesh& M)
{
    M.Normals.Init(FVector::ZeroVector,M.Positions.Num());
    for(int32 I=0;I+2<M.Triangles.Num();I+=3)
    { const int32 A=M.Triangles[I],B=M.Triangles[I+1],C=M.Triangles[I+2]; const FVector N=FVector::CrossProduct(M.Positions[B]-M.Positions[A],M.Positions[C]-M.Positions[A]); M.Normals[A]+=N; M.Normals[B]+=N; M.Normals[C]+=N; }
    for(auto& N:M.Normals) N=N.GetSafeNormal();
    M.Colors.Init(FLinearColor::White,M.Positions.Num()); M.Tangents.Init(FProcMeshTangent(1,0,0),M.Positions.Num());
    for(int I=0;I+2<M.Triangles.Num();I+=3) Swap(M.Triangles[I+1],M.Triangles[I+2]); // Blender RH to UE front-face winding; normals remain outward.
    if(M.UV.Num()!=M.Positions.Num()) { M.UV.Reset(); for(auto P:M.Positions) M.UV.Add(FVector2D(P.X*.12,P.Y*.12)); }
    A5Tangents(M);
}
FTrainingRenderMesh A5Cylinder(const FVector& A,const FVector& B,double Radius)
{
    FTrainingRenderMesh M; const FVector Z=(B-A).GetSafeNormal(); FVector X=FVector::CrossProduct(Z,FVector::UpVector).GetSafeNormal(); if(X.IsNearlyZero()) X=FVector::RightVector; const FVector Y=FVector::CrossProduct(Z,X);
    constexpr int32 N=24;
    for(int32 J=0;J<2;++J) for(int32 I=0;I<N;++I) { double Angle=2*PI*I/N; M.Positions.Add((J?B:A)+(X*FMath::Cos(Angle)+Y*FMath::Sin(Angle))*Radius); M.UV.Add(FVector2D(double(I)/N,J)); }
    for(int32 I=0;I<N;++I) { int32 K=(I+1)%N; M.Triangles.Append({I,K,K+N,I,K+N,I+N}); }
    M.Positions.Add(A);M.Positions.Add(B); M.UV.Add(FVector2D(.5,.5));M.UV.Add(FVector2D(.5,.5));
    for(int32 I=0;I<N;++I) { int32 K=(I+1)%N; M.Triangles.Append({2*N,K,I,2*N+1,I+N,K+N}); }
    A5Normals(M);return M;
}
bool A5Npy(const FString& Path,const void* Data,int64 Bytes,const FString& Type,const FString& Shape)
{
    FString Header=FString::Printf(TEXT("{'descr': '%s', 'fortran_order': False, 'shape': (%s), }"),*Type,*Shape);
    while((10+Header.Len()+1)%16) Header+=TEXT(" "); Header+=TEXT("\n");
    FTCHARToUTF8 H(*Header);TArray<uint8> File; const uint8 Magic[]={0x93,'N','U','M','P','Y',1,0,uint8(H.Length()&255),uint8((H.Length()>>8)&255)};
    File.Append(Magic,10);File.Append(reinterpret_cast<const uint8*>(H.Get()),H.Length());File.Append(static_cast<const uint8*>(Data),Bytes);return FFileHelper::SaveArrayToFile(File,*Path);
}
bool A5Vectors(const TSharedPtr<FJsonObject>& O,const TCHAR* Key,int Width,int Expected=-1)
{
    const TArray<TSharedPtr<FJsonValue>>* Values=nullptr;if(!O.IsValid()||!O->TryGetArrayField(Key,Values)||(Expected>=0&&Values->Num()!=Expected))return false;
    for(const auto& V:*Values){const TArray<TSharedPtr<FJsonValue>>* A=nullptr;if(!V->TryGetArray(A)||A->Num()!=Width)return false;for(const auto& N:*A){double D=0;if(!N->TryGetNumber(D)||!FMath::IsFinite(D)||FMath::Abs(D)>100000)return false;}}
    return true;
}
bool A5Numbers(const TSharedPtr<FJsonObject>& O,const TCHAR* Key,int Expected=-1)
{
    const TArray<TSharedPtr<FJsonValue>>* A=nullptr;if(!O.IsValid()||!O->TryGetArrayField(Key,A)||(Expected>=0&&A->Num()!=Expected))return false;
    for(const auto& V:*A){double D=0;if(!V->TryGetNumber(D)||!FMath::IsFinite(D))return false;}return true;
}
bool A5Mesh(const TSharedPtr<FJsonObject>& O)
{
    if(!A5Vectors(O,TEXT("vertices_m"),3)||!A5Vectors(O,TEXT("triangles"),3)||!A5Vectors(O,TEXT("uvs"),2,O->GetArrayField(TEXT("vertices_m")).Num()))return false;
    int Count=O->GetArrayField(TEXT("vertices_m")).Num();if(Count<3||Count>1000000)return false;
    for(const auto& F:O->GetArrayField(TEXT("triangles")))for(const auto& I:F->AsArray()){double V=I->AsNumber();if(V<0||V>=Count||V!=FMath::FloorToDouble(V))return false;}
    return true;
}
struct A5Triangle { FVector P[3]; int32 Id; };
}

void ATrainingScene::UpdatePhase5Tangents(FTrainingRenderMesh& M) const { A5Tangents(M); }

void ATrainingScene::ApplyPhase5Material(UProceduralMeshComponent* Mesh,const TSharedPtr<FJsonObject>& Material)
{
    if(Material.IsValid()) for(const TCHAR* Key:{TEXT("base_color_texture"),TEXT("normal_texture"),TEXT("roughness_texture")})
    {FString Relative;if(Material->TryGetStringField(Key,Relative)&&!Relative.IsEmpty()){const FString Full=FPaths::ConvertRelativePathToFull(FPaths::Combine(AnatomyDirectory,Relative));if(!FPaths::IsUnderDirectory(Full,AnatomyDirectory)){AnatomyError=TEXT("Anatomy texture path must stay inside asset directory");return;}}}
    auto* Base=LoadObject<UMaterialInterface>(nullptr,bPhase6?TEXT("/Game/Materials/M_AnatomyPhase6.M_AnatomyPhase6"):TEXT("/Game/Materials/M_Anatomy.M_Anatomy"));
    if(!Base) { AnatomyError=TEXT("M_Anatomy material missing; run asset generation"); Mesh->SetMaterial(0,TissueMaterial);return; }
    auto* M=UMaterialInstanceDynamic::Create(Base,this); FVector Color(.45,.2,.16);double Rough=.3,Metal=0;
    if(Material.IsValid())
    {
        const TArray<TSharedPtr<FJsonValue>>* C=nullptr;
        if(Material->TryGetArrayField(TEXT("base_color"),C) && C->Num()>=3) Color=FVector((*C)[0]->AsNumber(),(*C)[1]->AsNumber(),(*C)[2]->AsNumber());
        Material->TryGetNumberField(TEXT("roughness"),Rough);Material->TryGetNumberField(TEXT("metallic"),Metal);
        FString Texture;
        if(Material->TryGetStringField(TEXT("base_color_texture"),Texture) && !Texture.IsEmpty())
        {
            const FString Path=FPaths::Combine(AnatomyDirectory,Texture);
            if(UTexture2D* T=FImageUtils::ImportFileAsTexture2D(Path)) { M->SetTextureParameterValue(TEXT("BaseTexture"),T);M->SetScalarParameterValue(TEXT("TextureWeight"),1); Color=FVector::OneVector; }
            else AnatomyError=TEXT("Anatomy texture missing: ")+Path;
        }
        for(int Map=0;Map<2;++Map)
        {
            FString Relative;const TCHAR* Key=Map?TEXT("roughness_texture"):TEXT("normal_texture");
            if(Material->TryGetStringField(Key,Relative) && !Relative.IsEmpty())
            {
                if(UTexture2D* TextureMap=FImageUtils::ImportFileAsTexture2D(FPaths::Combine(AnatomyDirectory,Relative)))
                {TextureMap->SRGB=false;TextureMap->CompressionSettings=TC_VectorDisplacementmap;TextureMap->UpdateResource();M->SetTextureParameterValue(Map?TEXT("RoughnessTexture"):TEXT("NormalTexture"),TextureMap);double Strength=bPhase6?.45:.3;Material->TryGetNumberField(TEXT("normal_strength"),Strength);M->SetScalarParameterValue(Map?TEXT("RoughnessWeight"):TEXT("NormalWeight"),Map?1:Strength);}
                else AnatomyError=TEXT("Anatomy PBR map missing: ")+Relative;
            }
        }
    }
    M->SetVectorParameterValue(TEXT("BaseColor"),FLinearColor(Color.X,Color.Y,Color.Z,1));
    if(bPhase6 && Material.IsValid())
    {
        double Specular=.5,Opacity=.65;Material->TryGetNumberField(TEXT("specular"),Specular);Material->TryGetNumberField(TEXT("subsurface_opacity"),Opacity);
        M->SetScalarParameterValue(TEXT("Specular"),Specular);M->SetScalarParameterValue(TEXT("SubsurfaceOpacity"),Opacity);
        const TArray<TSharedPtr<FJsonValue>>* C=nullptr;
        if(Material->TryGetArrayField(TEXT("subsurface_color"),C)&&C->Num()>=3) M->SetVectorParameterValue(TEXT("SubsurfaceColor"),FLinearColor((*C)[0]->AsNumber(),(*C)[1]->AsNumber(),(*C)[2]->AsNumber(),1));
    }
    M->SetScalarParameterValue(TEXT("Roughness"),Rough);M->SetScalarParameterValue(TEXT("Metallic"),Metal);Mesh->SetMaterial(0,M);
}

void ATrainingScene::CreatePhase5Environment()
{
    if(!FParse::Value(FCommandLine::Get(),TEXT("LapAnatomyDir="),AnatomyDirectory))
        AnatomyDirectory=FPaths::ConvertRelativePathToFull(FPaths::Combine(FPaths::ProjectDir(),bPhase6?TEXT("../../Assets/Phase6"):TEXT("../../Assets/Phase5")));
    AnatomyDirectory=FPaths::ConvertRelativePathToFull(AnatomyDirectory);
    FString Raw;
    if(!FFileHelper::LoadFileToString(Raw,*FPaths::Combine(AnatomyDirectory,TEXT("scene.json"))) ||
       !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Raw),AnatomyAsset) || !AnatomyAsset.IsValid())
    { AnatomyError=TEXT("Cannot load anatomy scene.json: ")+AnatomyDirectory; UE_LOG(LogTemp,Error,TEXT("%s"),*AnatomyError); return; }
    FString SceneSchema,SceneUnits;const TSharedPtr<FJsonObject> *DynamicCheck=nullptr,*AttachmentCheck=nullptr;const TArray<TSharedPtr<FJsonValue>>* StaticCheck=nullptr;
    if(!AnatomyAsset->TryGetStringField(TEXT("schema"),SceneSchema)||SceneSchema!=TEXT("endoforge.anatomy-scene.v1")||!AnatomyAsset->TryGetStringField(TEXT("units"),SceneUnits)||SceneUnits!=TEXT("m")||!AnatomyAsset->TryGetObjectField(TEXT("dynamic_surface"),DynamicCheck)||!A5Mesh(*DynamicCheck)||!AnatomyAsset->TryGetObjectField(TEXT("attachment_bridge"),AttachmentCheck)||!A5Vectors(*AttachmentCheck,TEXT("anchors_m"),3)||!A5Vectors(*AttachmentCheck,TEXT("boundary_edges"),2)||!AnatomyAsset->TryGetArrayField(TEXT("static_objects"),StaticCheck)){AnatomyError=TEXT("Malformed anatomy schema or dynamic mesh");return;}
    const TSharedPtr<FJsonObject> *MaterialSetCheck=nullptr,*DynamicMaterialCheck=nullptr;double DynamicId=0;
    if(!AnatomyAsset->TryGetObjectField(TEXT("material_sets"),MaterialSetCheck)||!(*DynamicCheck)->TryGetObjectField(TEXT("material"),DynamicMaterialCheck)||!(*DynamicCheck)->TryGetNumberField(TEXT("id"),DynamicId)||DynamicId<1||DynamicId>=1000||DynamicId==500||DynamicId!=FMath::FloorToDouble(DynamicId)){AnatomyError=TEXT("Malformed anatomy materials or dynamic object ID");return;}
    const TSharedPtr<FJsonObject>* CameraCheck=nullptr;double CameraFov=0;
    if(!AnatomyAsset->TryGetObjectField(TEXT("camera"),CameraCheck)||!A5Numbers(*CameraCheck,TEXT("position_m"),3)||!A5Numbers(*CameraCheck,TEXT("target_m"),3)||!(*CameraCheck)->TryGetNumberField(TEXT("fov_degrees"),CameraFov)||!FMath::IsFinite(CameraFov)||CameraFov<10||CameraFov>120||!A5Numbers(*DynamicCheck,TEXT("material_vertex_ids"))||!A5Numbers(*AttachmentCheck,TEXT("surface_material_vertex_ids"))){AnatomyError=TEXT("Malformed anatomy camera or material identities");return;}
    for(const auto& V:*StaticCheck){const TSharedPtr<FJsonObject>* O=nullptr;if(!V->TryGetObject(O)||!A5Mesh(*O)){AnatomyError=TEXT("Malformed static anatomy geometry or UVs");return;}}
    TArray<uint8> PhysicsBytes;FString PhysicsText;TSharedPtr<FJsonObject> PhysicsAsset;
    const FString PhysicsPath=FPaths::Combine(AnatomyDirectory,TEXT("physics-mesh.json"));
    if(!FFileHelper::LoadFileToArray(PhysicsBytes,*PhysicsPath) || !FFileHelper::LoadFileToString(PhysicsText,*PhysicsPath) || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(PhysicsText),PhysicsAsset)) {AnatomyError=TEXT("Local physics anatomy asset unreadable");return;}
    const TSharedPtr<FJsonObject>* LiverCheck=nullptr;double Thickness=0;
    if(!A5Vectors(PhysicsAsset,TEXT("vertices_m"),3)||!A5Vectors(PhysicsAsset,TEXT("normals"),3)||!A5Vectors(PhysicsAsset,TEXT("triangles"),3)||!A5Numbers(PhysicsAsset,TEXT("attachment_vertex_ids"))||!A5Vectors(PhysicsAsset,TEXT("attachment_anchor_positions_m"),3)||!PhysicsAsset->TryGetObjectField(TEXT("static_liver"),LiverCheck)||!A5Vectors(*LiverCheck,TEXT("vertices_m"),3)||!A5Vectors(*LiverCheck,TEXT("triangles"),3)||!PhysicsAsset->TryGetNumberField(TEXT("thickness_m"),Thickness)||!FMath::IsFinite(Thickness)||Thickness<=0){AnatomyError=TEXT("Malformed local physics anatomy contract");return;}
    uint64 Fingerprint=14695981039346656037ULL;for(uint8 B:PhysicsBytes){Fingerprint^=B;Fingerprint*=1099511628211ULL;}
    AnatomyPhysicsFingerprint=FString::Printf(TEXT("fnv1a64:%016llx"),static_cast<unsigned long long>(Fingerprint));
    auto Same=[](const TSharedPtr<FJsonObject>& A,const TCHAR* KA,const TSharedPtr<FJsonObject>& B,const TCHAR* KB){const auto* X=A->Values.Find(KA);const auto* Y=B->Values.Find(KB);return X&&Y&&FJsonValue::CompareEqual(**X,**Y);};
    const auto DynamicAsset=AnatomyAsset->GetObjectField(TEXT("dynamic_surface"));const auto AttachmentAsset=AnatomyAsset->GetObjectField(TEXT("attachment_bridge"));
    bool Contract=Same(AnatomyAsset,TEXT("model_id"),PhysicsAsset,TEXT("model_id")) && Same(AnatomyAsset,TEXT("version"),PhysicsAsset,TEXT("version")) && Same(DynamicAsset,TEXT("triangles"),PhysicsAsset,TEXT("triangles")) && Same(AttachmentAsset,TEXT("surface_material_vertex_ids"),PhysicsAsset,TEXT("attachment_vertex_ids")) && Same(AttachmentAsset,TEXT("anchors_m"),PhysicsAsset,TEXT("attachment_anchor_positions_m"));
    const auto& PV=PhysicsAsset->GetArrayField(TEXT("vertices_m"));const auto& PN=PhysicsAsset->GetArrayField(TEXT("normals"));const auto& DV=DynamicAsset->GetArrayField(TEXT("vertices_m"));const auto& DI=DynamicAsset->GetArrayField(TEXT("material_vertex_ids"));
    Contract &= PV.Num()==DV.Num() && PV.Num()==PN.Num() && PV.Num()==DI.Num();
    if(Contract)for(int I=0;I<PV.Num();++I)Contract &= int(DI[I]->AsNumber())==I && FVector::Distance(A5Read(PV[I])+A5Read(PN[I])*PhysicsAsset->GetNumberField(TEXT("thickness_m"))*.5,A5Read(DV[I]))<1e-10;
    bool LiverMatched=false;TSet<int32> ObjectIds;ObjectIds.Add(DynamicAsset->GetIntegerField(TEXT("id")));ObjectIds.Add(500);
    for(const auto& O:AnatomyAsset->GetArrayField(TEXT("static_objects")))
    {
        const auto Obj=O->AsObject();const int32 Id=Obj->GetIntegerField(TEXT("id"));Contract &= Id>0 && Id<1000 && !ObjectIds.Contains(Id);ObjectIds.Add(Id);
        if(Id==200){auto Liver=PhysicsAsset->GetObjectField(TEXT("static_liver"));LiverMatched=Same(Obj,TEXT("vertices_m"),Liver,TEXT("vertices_m"))&&Same(Obj,TEXT("triangles"),Liver,TEXT("triangles"));}
    }
    if(!Contract||!LiverMatched){AnatomyError=TEXT("Scene and local physics geometry/IDs/liver-bed contract mismatch");return;}
    const TArray<TSharedPtr<FJsonValue>>* Objects=nullptr;
    if(!AnatomyAsset->TryGetArrayField(TEXT("static_objects"),Objects)) { AnatomyError=TEXT("static_objects missing");return; }
    for(const auto& Value:*Objects)
    {
        auto O=Value->AsObject();if(!O.IsValid()) continue;
        const TSharedPtr<FJsonObject>* Display=nullptr;auto G=O;
        if(bPhase6 && O->TryGetObjectField(TEXT("display_mesh"),Display)) G=*Display;
        if(!A5Mesh(G)) {AnatomyError=TEXT("Malformed high detail static anatomy mesh");return;}
        FTrainingRenderMesh M;
        for(const auto& V:G->GetArrayField(TEXT("vertices_m"))) M.Positions.Add(A5Read(V,100));
        for(const auto& T:G->GetArrayField(TEXT("triangles"))) for(const auto& I:T->AsArray()) M.Triangles.Add(int32(I->AsNumber()));
        bool Valid=M.Positions.Num()>=3 && M.Triangles.Num()%3==0;
        for(int32 I:M.Triangles) Valid&=M.Positions.IsValidIndex(I);
        for(auto P:M.Positions) Valid&=!P.ContainsNaN();
        if(!Valid) { AnatomyError=TEXT("Malformed static anatomy mesh");return; }
        const TArray<TSharedPtr<FJsonValue>>* UV=nullptr;
        if(G->TryGetArrayField(TEXT("uvs"),UV)) for(const auto& U:*UV) { const auto& A=U->AsArray(); if(A.Num()==2) M.UV.Add(FVector2D(A[0]->AsNumber(),1-A[1]->AsNumber())); }
        A5Normals(M);
        const FString Name=O->GetStringField(TEXT("name"));
        auto* P=NewObject<UProceduralMeshComponent>(this,FName(*(TEXT("Anatomy_")+Name)));P->SetupAttachment(SceneRoot);P->SetCollisionEnabled(ECollisionEnabled::NoCollision);P->SetSimulatePhysics(false);P->RegisterComponent();
        P->CreateMeshSection_LinearColor(0,M.Positions,M.Triangles,M.Normals,M.UV,M.Colors,M.Tangents,false);
        const TSharedPtr<FJsonObject>* Mat=nullptr;O->TryGetObjectField(TEXT("material"),Mat);ApplyPhase5Material(P,Mat?*Mat:nullptr);
        AnatomyMeshes.Add(P);AnatomyNames.Add(Name);double Id=AnatomyMeshes.Num()+1;O->TryGetNumberField(TEXT("id"),Id);AnatomyIds.Add(int32(Id));
        if(bPhase6 && !BuildPhase6StaticDisplay(P,O)) return;
    }
    const TSharedPtr<FJsonObject>* TissueMat=nullptr;
    const TSharedPtr<FJsonObject>* Dynamic=nullptr;
    if(AnatomyAsset->TryGetObjectField(TEXT("dynamic_surface"),Dynamic)) {(*Dynamic)->TryGetObjectField(TEXT("material"),TissueMat);AnatomyGallbladderId=(*Dynamic)->GetIntegerField(TEXT("id"));}
    ApplyPhase5Material(TissueMesh,TissueMat?*TissueMat:nullptr);
    auto* Light=NewObject<USpotLightComponent>(this,TEXT("AnatomyEndoscopeLight"));EndoscopeLight=Light;Light->SetupAttachment(Camera);Light->SetMobility(EComponentMobility::Movable);Light->SetIntensityUnits(ELightUnits::Candelas);Light->SetIntensity(.08);Light->SetLightColor(FLinearColor(1,.89,.76));Light->SetAttenuationRadius(100);Light->SetInnerConeAngle(34);Light->SetOuterConeAngle(54);Light->SetSourceRadius(.45);Light->SetCastShadows(true);Light->RegisterComponent();Light->SetRelativeLocation(FVector(0,.35,.15));
    if(!bPhase6) {auto* Fill=NewObject<UPointLightComponent>(this,TEXT("AnatomyReflectedFill"));Fill->SetupAttachment(Camera);Fill->SetIntensityUnits(ELightUnits::Candelas);Fill->SetIntensity(.008);Fill->SetLightColor(FLinearColor(1,.6,.4));Fill->SetAttenuationRadius(45);Fill->SetSourceRadius(4);Fill->SetCastShadows(false);Fill->RegisterComponent();}
    AnatomyAttachment=NewObject<UProceduralMeshComponent>(this,TEXT("HepaticAttachmentMembrane"));AnatomyAttachment->SetupAttachment(SceneRoot);AnatomyAttachment->SetCollisionEnabled(ECollisionEnabled::NoCollision);AnatomyAttachment->RegisterComponent();
    const TSharedPtr<FJsonObject>* Attachment=nullptr;if(AnatomyAsset->TryGetObjectField(TEXT("attachment_bridge"),Attachment)) ApplyPhase5Material(AnatomyAttachment,(*Attachment)->GetObjectField(TEXT("material")));
    TissueMesh->SetVisibility(false);
    UE_LOG(LogTemp,Display,TEXT("LAP_PHASE5_ASSETS %s static_objects=%d"),*AnatomyDirectory,AnatomyMeshes.Num());
}

void ATrainingScene::InitializePhase5()
{
    bPhase5Test=FParse::Param(FCommandLine::Get(),TEXT("LapPhase5Test")) || FParse::Param(FCommandLine::Get(),TEXT("LapPhase6Test"));
    if(!FParse::Value(FCommandLine::Get(),TEXT("LapCaptureDir="),Phase5Directory)) Phase5Directory=FPaths::Combine(FPaths::ProjectSavedDir(),TEXT("Phase5"),FDateTime::UtcNow().ToString(TEXT("%Y%m%d-%H%M%S")));
    Phase5Directory=FPaths::ConvertRelativePathToFull(Phase5Directory);IFileManager::Get().MakeDirectory(*Phase5Directory,true);Phase4Directory=Phase5Directory;
    for(auto S:SceneMeshes) S->SetHiddenInGame(true);
    for(int32 I=0;I<4;++I) { auto* P=NewObject<UProceduralMeshComponent>(this,FName(*FString::Printf(TEXT("AnatomyShaft%d"),I)));P->SetupAttachment(SceneRoot);P->SetCollisionEnabled(ECollisionEnabled::NoCollision);P->RegisterComponent();P->SetMaterial(0,I%2?InsulationMaterial.Get():MetalMaterial.Get());AnatomyRods.Add(P); }
    UpdatePhase5Rods();
    if(AnatomyError.IsEmpty()) WritePhase5Manifest();
    UE_LOG(LogTemp,Display,TEXT("LAP_PHASE5 output=%s test=%d"),*Phase5Directory,bPhase5Test);
}

void ATrainingScene::WritePhase5Manifest()
{
    const FString Dir=FPaths::Combine(Phase5Directory,TEXT("dataset"));IFileManager::Get().MakeDirectory(*Dir,true);
    auto O=MakeShared<FJsonObject>();O->SetStringField(TEXT("schema"),TEXT("endoforge.phase5.visual_manifest.v1"));O->SetStringField(TEXT("hash_algorithm"),TEXT("SHA1"));O->SetStringField(TEXT("physics_fingerprint"),AnatomyPhysicsFingerprint);O->SetStringField(TEXT("engine_version"),FEngineVersion::Current().ToString());O->SetStringField(TEXT("render_build"),TEXT("EndoForge Phase5 UE module ")+FString(ANSI_TO_TCHAR(__DATE__ " " __TIME__)));
    auto HashFile=[](const FString& Path){TArray<uint8> B;if(!FFileHelper::LoadFileToArray(B,*Path))return FString();uint8 H[20];FSHA1::HashBuffer(B.GetData(),B.Num(),H);return BytesToHex(H,20).ToLower();};
    auto Files=MakeShared<FJsonObject>();Files->SetStringField(TEXT("scene.json"),HashFile(FPaths::Combine(AnatomyDirectory,TEXT("scene.json"))));Files->SetStringField(TEXT("physics-mesh.json"),HashFile(FPaths::Combine(AnatomyDirectory,TEXT("physics-mesh.json"))));
    TArray<FString> Textures;IFileManager::Get().FindFilesRecursive(Textures,*FPaths::Combine(AnatomyDirectory,TEXT("textures")),TEXT("*.png"),true,false);
    for(FString Path:Textures){FString Relative=Path;FPaths::MakePathRelativeTo(Relative,*(AnatomyDirectory+TEXT("/")));Files->SetStringField(Relative,HashFile(Path));}O->SetObjectField(TEXT("asset_file_hashes"),Files);
    O->SetStringField(TEXT("asset_path_base"),bPhase6?TEXT("Phase6 anatomy asset directory; copy Assets alongside dataset for full reproducibility"):TEXT("Phase5 anatomy asset directory; copy Assets alongside dataset for full reproducibility"));
    O->SetStringField(TEXT("material_interpretation"),TEXT("Authored base PNG sampled sRGB; normal and roughness PNG sampled linear uncompressed RGBA; Blender V flipped for UE, normal green inverted; UV-derived tangent basis; normal 2RGB-1 blended with tangent flat at strength 0.3; opaque two-sided wet PBR, no WPO/displacement. Geometric normal labels exclude normal maps."));
    if(bPhase6)
    {
        O->SetNumberField(TEXT("phase"),6);
        O->SetStringField(TEXT("render_build"),TEXT("EndoForge Phase6 UE module ")+FString(ANSI_TO_TCHAR(__DATE__ " " __TIME__)));
        O->SetStringField(TEXT("material_interpretation"),TEXT("Original base PNG sRGB; roughness/normal linear. Blender V flipped for UE and normal green inverted. Authored normal_strength, specular, subsurface_color and subsurface_opacity. Opaque two-sided Subsurface shading, no WPO. Static mesh Lumen cards and hardware ray tracing; bounded cubic PN dynamic surface maximum 0.12mm. Labels export actual high-detail triangles; geometric normals exclude shader normal maps."));
    }
    O->SetObjectField(TEXT("authored_materials"),AnatomyAsset->GetObjectField(TEXT("material_sets")));
    TArray<TSharedPtr<FJsonValue>> Lights;TArray<ULightComponent*> Components;GetComponents(Components);
    for(auto* Light:Components){auto L=MakeShared<FJsonObject>();L->SetStringField(TEXT("name"),Light->GetName());L->SetStringField(TEXT("class"),Light->GetClass()->GetName());L->SetNumberField(TEXT("intensity"),Light->Intensity);L->SetField(TEXT("position_cm"),A5V(Light->GetComponentLocation()));L->SetField(TEXT("forward"),A5V(Light->GetForwardVector()));const auto C=Light->GetLightColor();L->SetArrayField(TEXT("linear_color"),{MakeShared<FJsonValueNumber>(C.R),MakeShared<FJsonValueNumber>(C.G),MakeShared<FJsonValueNumber>(C.B)});L->SetBoolField(TEXT("cast_shadows"),Light->CastShadows);L->SetStringField(TEXT("intensity_units"),TEXT("candela"));if(auto* Spot=Cast<USpotLightComponent>(Light)){L->SetNumberField(TEXT("inner_cone_deg"),Spot->InnerConeAngle);L->SetNumberField(TEXT("outer_cone_deg"),Spot->OuterConeAngle);}Lights.Add(MakeShared<FJsonValueObject>(L));}O->SetArrayField(TEXT("lights"),Lights);
    O->SetStringField(TEXT("exposure"),TEXT("manual exposure, physical-camera-exposure disabled, EV bias 0; no motion blur; stereo capture AA disabled, final-color-LDR PNG; main viewport may use project AA"));
    const FString Manifest=FPaths::Combine(Dir,TEXT("visual-manifest.json"));A5Save(Manifest,O);AnatomyVisualFingerprint=HashFile(Manifest);
}

void ATrainingScene::UpdatePhase5Attachment()
{
    if(!AnatomyAttachment || !Bridge || !AnatomyAsset.IsValid())return;
    const TSharedPtr<FJsonObject>* A=nullptr;if(!AnatomyAsset->TryGetObjectField(TEXT("attachment_bridge"),A))return;
    const auto& Ids=(*A)->GetArrayField(TEXT("surface_material_vertex_ids"));const auto& Anchors=(*A)->GetArrayField(TEXT("anchors_m"));const auto& Edges=(*A)->GetArrayField(TEXT("boundary_edges"));const auto& Materials=Bridge->GetMaterialIds();
    const auto& State=Bridge->GetAcceptedState();const TArray<TSharedPtr<FJsonValue>>* Segments=nullptr;
    if(!State.IsValid()||!State->TryGetArrayField(TEXT("attachment_segments_m"),Segments)||Segments->Num()!=Ids.Num()){AnatomyError=TEXT("Native liver-bed spring endpoint count mismatch");return;}
    FTrainingRenderMesh M;TMap<int32,int32> IdMap;
    for(int I=0;I<Ids.Num();++I)
    {
        const TArray<TSharedPtr<FJsonValue>>* Pair=nullptr;if(!(*Segments)[I]->TryGetArray(Pair)||Pair->Num()!=2){AnatomyError=TEXT("Invalid native liver-bed spring endpoints");return;}
        auto Verify=MakeShared<FJsonObject>();Verify->SetArrayField(TEXT("points"),*Pair);if(!A5Vectors(Verify,TEXT("points"),3,2)){AnatomyError=TEXT("Nonfinite native liver-bed spring endpoints");return;}
        int32 Id=int32(Ids[I]->AsNumber());IdMap.Add(Id,I*2);
        // Native endpoints identify the exact outer wall node used by the physical spring.
        M.Positions.Add(A5Read((*Pair)[0],100));M.Positions.Add(A5Read((*Pair)[1],100));M.UV.Add(FVector2D(I*.1,0));M.UV.Add(FVector2D(I*.1,1));
    }
    for(const auto& E:Edges) {const auto& V=E->AsArray();if(V.Num()!=2)continue;const int32* X=IdMap.Find(int32(V[0]->AsNumber()));const int32* Y=IdMap.Find(int32(V[1]->AsNumber()));if(X&&Y)M.Triangles.Append({*X,*Y,*Y+1,*X,*Y+1,*X+1});}
    A5Normals(M);AnatomyAttachment->CreateMeshSection_LinearColor(0,M.Positions,M.Triangles,M.Normals,M.UV,M.Colors,M.Tangents,false);
}

void ATrainingScene::UpdatePhase5Rods()
{
    if(AnatomyRods.Num()!=4) return;
    for(int32 T=0;T<2;++T)
    {
        const FVector P=GetPivot(T),Axis=(P-ActualTips[T]).GetSafeNormal(),Joint=ActualTips[T]+Axis*1.45;
        for(int32 J=0;J<2;++J)
        {
            auto M=A5Cylinder(J?Joint+Axis*3:Joint+Axis*.25,J?P-Axis*.35:P+Axis*1.5,J?.205:.20);
            AnatomyRods[T*2+J]->CreateMeshSection_LinearColor(0,M.Positions,M.Triangles,M.Normals,M.UV,M.Colors,M.Tangents,false);
        }
    }
}

bool ATrainingScene::AdoptPhase5Metadata()
{
    if(!AnatomyError.IsEmpty()||!AnatomyAsset.IsValid())return false;
    const auto& M=Bridge->GetModelMetadata();if(!M.IsValid()) return false;
    if(M->GetStringField(TEXT("asset_fingerprint"))!=AnatomyPhysicsFingerprint){AnatomyError=TEXT("Native physics asset differs from local rendering anatomy bytes");return false;}
    const TArray<TSharedPtr<FJsonValue>> *Homes=nullptr,*Targets=nullptr;
    if(!A5Vectors(M,TEXT("home_tips_m"),3,2)||!A5Vectors(M,TEXT("grasp_targets_m"),3,2)||!M->TryGetArrayField(TEXT("home_tips_m"),Homes)||Homes->Num()!=2 || !M->TryGetArrayField(TEXT("grasp_targets_m"),Targets)||Targets->Num()!=2)
    { AnatomyError=TEXT("Native anatomy grasp/home metadata missing");return false; }
    for(int I=0;I<2;++I) { Phase5Homes[I]=A5Read((*Homes)[I],100);Phase5Targets[I]=A5Read((*Targets)[I],100);ToolTips[I]=Phase5Homes[I]; }
    if(bPhase6)
    {
        ResetPhase6Motion();
        const TSharedPtr<FJsonObject>* Recipes=nullptr;
        const TArray<TSharedPtr<FJsonValue>>* Entries=nullptr;
        FString Schema;
        if(!M->TryGetObjectField(TEXT("phase6_ready_recipes"),Recipes) ||
            !(*Recipes)->TryGetStringField(TEXT("schema"),Schema) || Schema!=TEXT("endoforge.phase6.ready_recipes.v1") ||
            !(*Recipes)->TryGetArrayField(TEXT("recipes"),Entries) || Entries->Num()!=2)
        { AnatomyError=TEXT("Native Phase 6 ready recipes are missing or incompatible");return false; }
        for(int32 I=0;I<2;++I)
        {
            const TSharedPtr<FJsonObject>* Recipe=nullptr;
            double ToolIndex=-1,Roll=0;FVector Ready;
            if(!(*Entries)[I]->TryGetObject(Recipe) || !(*Recipe)->TryGetNumberField(TEXT("tool"),ToolIndex) || ToolIndex!=I ||
                !(*Recipe)->TryGetNumberField(TEXT("roll_deg"),Roll) || !FMath::IsFinite(Roll) || FMath::Abs(Roll)>360 ||
                !A5FiniteVector(*Recipe,TEXT("rest_ready_tip_m"),Ready,100))
            { AnatomyError=TEXT("Native Phase 6 ready recipe contains an invalid pose");return false; }
            Phase6ReadyRecipes[I]=*Recipe;Phase6ReadyRolls[I]=Roll;Phase5Targets[I]=Ready;
        }
    }
    bPhase5HomeAdopted=true;LoadActiveCommand();TissueMesh->SetVisibility(true);
    AnatomyModelId=M->GetStringField(TEXT("model_id"));if(!M->TryGetStringField(TEXT("model_version"),AnatomyModelVersion)) AnatomyModelVersion=FString::Printf(TEXT("%.0f"),M->GetNumberField(TEXT("model_version")));
    if(AnatomyAsset->GetStringField(TEXT("model_id"))!=AnatomyModelId || FString::Printf(TEXT("%.0f"),AnatomyAsset->GetNumberField(TEXT("version")))!=AnatomyModelVersion) { AnatomyError=TEXT("Scene and physics model identity differ");TissueMesh->SetVisibility(false);return false; }
    return true;
}

bool ATrainingScene::SamplePhase6ReadyTarget(int32 Index,const FString& Source,FVector& OutTarget)
{
    if(!bPhase6 || Index<0 || Index>1 || !Bridge || !Bridge->IsHealthy() ||
        !Bridge->HasAcknowledgedReset() || Bridge->IsFrozenResumePending() ||
        !bPhase5HomeAdopted || !AnatomyError.IsEmpty() || !AnatomyAsset.IsValid()) return false;
    auto Invalid=[&](const TCHAR* Reason)
    { AnatomyError=FString(TEXT("Material-bound ready target rejected: "))+Reason;UE_LOG(LogTemp,Error,TEXT("%s"),*AnatomyError);return false; };
    TArray<FVector> Current;TArray<int32> Faces;
    if(!Bridge->GetSurface(Current,Faces)) return false;
    const auto Dynamic=AnatomyAsset->GetObjectField(TEXT("dynamic_surface"));
    const auto& Rest=Dynamic->GetArrayField(TEXT("vertices_m"));
    const auto& RestFaces=Dynamic->GetArrayField(TEXT("triangles"));
    const auto& AuthoredIds=Dynamic->GetArrayField(TEXT("material_vertex_ids"));
    const auto& NodeIds=Bridge->GetNodeIds();const auto& MaterialIds=Bridge->GetMaterialIds();
    const int32 Count=Rest.Num();
    // The fingerprint-validated anatomy exports the outer wall first, followed
    // by the inner wall. Cutting is disabled for this model. Reject a changed
    // identity/order instead of applying a binding to a different material.
    if(Count<3 || AuthoredIds.Num()!=Count || Current.Num()!=Count*2 ||
        NodeIds.Num()!=Current.Num() || MaterialIds.Num()!=Current.Num() ||
        Faces.Num()!=RestFaces.Num()*6) return Invalid(TEXT("native wall size differs from the validated anatomy"));
    for(int32 I=0;I<Current.Num();++I)
        if(NodeIds[I]!=I || MaterialIds[I]!=I || Current[I].ContainsNaN() ||
            (I<Count && AuthoredIds[I]->AsNumber()!=I)) return Invalid(TEXT("native node/material identity or order changed"));
    double Best=MAX_dbl;int32 BestFace=INDEX_NONE,A=0,B=0,C=0;
    FVector RestPoint=FVector::ZeroVector,Weights=FVector::ZeroVector;
    const FVector OriginalTip=Phase5Targets[Index];
    const auto* Tool=Bridge->GetToolState(Index);
    if(!Tool || Tool->JawPoses.Num()!=2) return Invalid(TEXT("authoritative jaw frames unavailable"));
    const FVector ActualAxis=(Tool->PivotCm-Tool->ActualTipCm).GetSafeNormal();
    const FVector MeanJawCenter=(Tool->JawPoses[0].CenterCm+Tool->JawPoses[1].CenterCm)*.5;
    const FVector MeanJawForward=(Tool->JawPoses[0].Axis+Tool->JawPoses[1].Axis)*.5;
    // Native jaw centers are tip + shaftAxis*L + jawForward*(L/2),
    // plus opposite lateral offsets which cancel in the pair mean. Recover L
    // to check the accepted geometry; use the recipe's explicit binding below.
    const FVector CenterAxis=ActualAxis+MeanJawForward*.5;
    const double JawLengthCm=FVector::DotProduct(MeanJawCenter-Tool->ActualTipCm,CenterAxis)/CenterAxis.SizeSquared();
    if(!FMath::IsFinite(JawLengthCm)||JawLengthCm<=0||
        FVector::Distance(MeanJawCenter,Tool->ActualTipCm+CenterAxis*JawLengthCm)>1.e-5)
        return Invalid(TEXT("native jaw frames do not define a consistent contact-center geometry"));
    const auto& Recipe=Phase6ReadyRecipes[Index];
    const TSharedPtr<FJsonObject>* Binding=nullptr;FVector RestContactQuery;
    if(!Recipe.IsValid() || !Recipe->TryGetObjectField(TEXT("material_binding"),Binding) ||
        !A5FiniteVector(*Binding,TEXT("rest_query_m"),RestContactQuery,100))
        return Invalid(TEXT("shared native material binding query is missing or invalid"));
    // The native recipe states the material query explicitly. It may refer to
    // a reference pose before an authored insertion offset, so reconstructing
    // it from the final tip would silently bind a different tissue location.
    for(int32 F=0;F<RestFaces.Num();++F)
    {
        const auto& Triangle=RestFaces[F]->AsArray();
        if(Triangle.Num()!=3) return Invalid(TEXT("invalid authored outer-wall triangle"));
        const int32 IA=int32(Triangle[0]->AsNumber()),IB=int32(Triangle[1]->AsNumber()),IC=int32(Triangle[2]->AsNumber());
        if(!Rest.IsValidIndex(IA)||!Rest.IsValidIndex(IB)||!Rest.IsValidIndex(IC)||
            Faces[F*3]!=IA||Faces[F*3+1]!=IB||Faces[F*3+2]!=IC)
            return Invalid(TEXT("native outer-wall topology differs from the bound rest surface"));
        const FVector RA=A5Read(Rest[IA],100),RB=A5Read(Rest[IB],100),RC=A5Read(Rest[IC],100);
        if(FVector::CrossProduct(RB-RA,RC-RA).SizeSquared()<1.e-20) return Invalid(TEXT("degenerate rest triangle"));
        const FVector Point=FMath::ClosestPointOnTriangleToPoint(RestContactQuery,RA,RB,RC);
        const double Distance=FVector::DistSquared(Point,RestContactQuery);
        if(Distance<Best)
        { Best=Distance;BestFace=F;A=IA;B=IB;C=IC;RestPoint=Point;Weights=FMath::ComputeBaryCentric2D(Point,RA,RB,RC); }
    }
    if(BestFace==INDEX_NONE || Weights.ContainsNaN() || FMath::Abs(Weights.X+Weights.Y+Weights.Z-1)>1.e-8 ||
        FMath::Min3(Weights.X,Weights.Y,Weights.Z)<-1.e-8) return Invalid(TEXT("invalid closest material-point binding"));
    double BoundFace=-1;FVector BoundNodes,BoundWeights,BoundRest,BoundQuery,BoundOffset;
    if(!(*Binding)->TryGetNumberField(TEXT("triangle_id"),BoundFace) || !FMath::IsFinite(BoundFace) ||
        BoundFace!=FMath::FloorToDouble(BoundFace) || BoundFace<0 || BoundFace>=RestFaces.Num() ||
        !A5FiniteVector(*Binding,TEXT("node_ids"),BoundNodes) || !A5FiniteVector(*Binding,TEXT("barycentric"),BoundWeights) ||
        !A5FiniteVector(*Binding,TEXT("rest_surface_point_m"),BoundRest,100) ||
        !A5FiniteVector(*Binding,TEXT("rest_query_m"),BoundQuery,100) ||
        !A5FiniteVector(*Binding,TEXT("tip_offset_m"),BoundOffset,100))
        return Invalid(TEXT("shared native material binding is missing or invalid"));
    const auto& BoundTriangle=RestFaces[int32(BoundFace)]->AsArray();
    for(int32 I=0;I<3;++I)
        if(BoundNodes[I]!=BoundTriangle[I]->AsNumber())return Invalid(TEXT("shared binding node identity differs from authored topology"));
    const FVector ExpectedRest=A5Read(Rest[int32(BoundNodes.X)],100)*BoundWeights.X+
        A5Read(Rest[int32(BoundNodes.Y)],100)*BoundWeights.Y+A5Read(Rest[int32(BoundNodes.Z)],100)*BoundWeights.Z;
    if(FMath::Abs(BoundWeights.X+BoundWeights.Y+BoundWeights.Z-1)>1.e-8 ||
        FMath::Min3(BoundWeights.X,BoundWeights.Y,BoundWeights.Z)<-1.e-8 ||
        FVector::Distance(ExpectedRest,BoundRest)>1.e-7 || FVector::Distance(RestContactQuery,BoundQuery)>1.e-7 ||
        FVector::Distance(OriginalTip-BoundRest,BoundOffset)>1.e-7 ||
        FVector::Distance(BoundRest,RestContactQuery)>FMath::Sqrt(Best)+1.e-7)
        return Invalid(TEXT("shared binding does not reproduce the validated closest material point"));
    BestFace=int32(BoundFace);A=int32(BoundNodes.X);B=int32(BoundNodes.Y);C=int32(BoundNodes.Z);
    Weights=BoundWeights;RestPoint=BoundRest;
    const FVector CurrentPoint=Current[A]*Weights.X+Current[B]*Weights.Y+Current[C]*Weights.Z;
    const FVector Offset=OriginalTip-RestPoint;
    OutTarget=CurrentPoint+Offset;
    if(OutTarget.ContainsNaN()) return Invalid(TEXT("nonfinite bound ready target"));
    const TArray<TSharedPtr<FJsonValue>>* Descriptors=nullptr;
    if(!Recipe->TryGetArrayField(TEXT("approach_waypoints"),Descriptors) || Descriptors->Num()>8)
        return Invalid(TEXT("shared approach waypoint descriptors missing or excessive"));
    TArray<FVector> ResolvedWaypoints;TArray<TSharedPtr<FJsonValue>> RecordedWaypoints;FVector Cursor=Tool->ActualTipCm;
    for(const auto& Value:*Descriptors)
    {
        const TSharedPtr<FJsonObject>* Descriptor=nullptr;FString Kind;FVector Point;
        if(!Value->TryGetObject(Descriptor) || !(*Descriptor)->TryGetStringField(TEXT("kind"),Kind))
            return Invalid(TEXT("invalid shared waypoint descriptor"));
        if(Kind==TEXT("current_xy_at_z"))
        {
            double Z=0;if(!(*Descriptor)->TryGetNumberField(TEXT("z_m"),Z) || !FMath::IsFinite(Z) || Z<-.002 || Z>.08)
                return Invalid(TEXT("invalid approach clearance height"));
            Point=Cursor;Point.Z=Z*100;
        }
        else if(Kind==TEXT("toward_pivot_from_frozen_ready"))
        {
            double Distance=0;if(!(*Descriptor)->TryGetNumberField(TEXT("distance_m"),Distance) ||
                !FMath::IsFinite(Distance) || Distance<0 || Distance>.08)
                return Invalid(TEXT("invalid axial approach distance"));
            Point=OutTarget+(Tool->PivotCm-OutTarget).GetSafeNormal()*Distance*100;
        }
        else return Invalid(TEXT("unknown shared approach waypoint kind"));
        Cursor=Point;ResolvedWaypoints.Add(Point);RecordedWaypoints.Add(A5V(Point));
    }
    ResolvedWaypoints.Add(OutTarget);RecordedWaypoints.Add(A5V(OutTarget));
    Phase6SampledApproachWaypoints[Index]=ResolvedWaypoints;Phase6SampledReadyTargets[Index]=OutTarget;
    auto Sample=MakeShared<FJsonObject>();Sample->SetStringField(TEXT("source"),Source);Sample->SetNumberField(TEXT("tool"),Index);
    Sample->SetStringField(TEXT("binding"),TEXT("shared native recipe's explicit rest query and closest authored outer-wall triangle; barycentric material point plus original world-space tip-to-surface offset"));
    Sample->SetStringField(TEXT("model_id"),AnatomyModelId);Sample->SetStringField(TEXT("model_version"),AnatomyModelVersion);
    Sample->SetStringField(TEXT("asset_fingerprint"),AnatomyPhysicsFingerprint);Sample->SetBoolField(TEXT("native_material_identity_and_outer_topology_verified"),true);
    Sample->SetNumberField(TEXT("state_id"),Bridge->GetStateId());Sample->SetNumberField(TEXT("simulation_id"),Bridge->GetSimulationId());
    Sample->SetNumberField(TEXT("topology_revision"),Bridge->GetTopologyRevision());Sample->SetNumberField(TEXT("native_time_s"),Bridge->GetNativeTime());
    Sample->SetNumberField(TEXT("rest_triangle_id"),BestFace);Sample->SetField(TEXT("material_node_ids"),A5V(FVector(A,B,C)));
    Sample->SetField(TEXT("barycentric_weights"),A5V(Weights));Sample->SetField(TEXT("original_ready_tip_cm"),A5V(OriginalTip));
    Sample->SetField(TEXT("rest_material_binding_query_cm"),A5V(RestContactQuery));Sample->SetNumberField(TEXT("jaw_length_from_native_frames_mm"),JawLengthCm*10);
    Sample->SetField(TEXT("rest_surface_point_cm"),A5V(RestPoint));Sample->SetField(TEXT("current_surface_point_cm"),A5V(CurrentPoint));
    Sample->SetField(TEXT("preserved_tip_offset_cm"),A5V(Offset));Sample->SetField(TEXT("sampled_ready_tip_cm"),A5V(OutTarget));
    Sample->SetField(TEXT("target_displacement_mm"),A5V((OutTarget-OriginalTip)*10));
    Sample->SetNumberField(TEXT("target_displacement_magnitude_mm"),FVector::Distance(OutTarget,OriginalTip)*10);
    Sample->SetBoolField(TEXT("sampled_once_at_approach_start"),true);Phase6ReadyTargetSamples.Add(MakeShared<FJsonValueObject>(Sample));
    Sample->SetStringField(TEXT("recipe_schema"),TEXT("endoforge.phase6.ready_recipes.v1"));
    Sample->SetObjectField(TEXT("recipe"),Recipe);Sample->SetNumberField(TEXT("ready_roll_deg"),Phase6ReadyRolls[Index]);
    Sample->SetArrayField(TEXT("resolved_approach_waypoints_cm"),RecordedWaypoints);
    auto Audit=MakeShared<FJsonObject>();Audit->SetStringField(TEXT("schema"),TEXT("endoforge.phase6.material_ready_targets.v1"));Audit->SetArrayField(TEXT("samples"),Phase6ReadyTargetSamples);
    if(!A5Save(FPaths::Combine(Phase5Directory,TEXT("phase6-ready-targets.json")),Audit))
        Phase6FoundationFailures.AddUnique(TEXT("Failed to save material-bound ready target provenance"));
    UE_LOG(LogTemp,Display,TEXT("LAP_PHASE6_READY_TARGET source=%s tool=%d state=%llu triangle=%d rest_cm=%s sampled_cm=%s displacement_mm=%.6f frozen_for_approach=1"),
        *Source,Index,static_cast<unsigned long long>(Bridge->GetStateId()),BestFace,*OriginalTip.ToString(),*OutTarget.ToString(),FVector::Distance(OutTarget,OriginalTip)*10);
    return true;
}

TSharedRef<FJsonObject> ATrainingScene::BuildPhase5RenderGeometry() const
{
    double Heartbeat=FPlatformTime::Seconds();
    auto Root=MakeShared<FJsonObject>();Root->SetStringField(TEXT("schema"),TEXT("endoforge.phase5.render_geometry.v1"));Root->SetStringField(TEXT("units"),TEXT("cm"));
    TArray<TSharedPtr<FJsonValue>> Objects;
    auto Add=[&](UProceduralMeshComponent* P,int32 Id,const FString& Name)
    {
        if(!P || (!P->IsVisible() && !(bPhase6 && AnatomyMeshes.Contains(P)))) return;const auto* S=P->GetProcMeshSection(0);if(!S) return;
        auto O=MakeShared<FJsonObject>();O->SetNumberField(TEXT("object_id"),Id);O->SetStringField(TEXT("name"),Name);
        TArray<TSharedPtr<FJsonValue>> V,N,T,UV;
        for(const auto& Q:S->ProcVertexBuffer)
        { V.Add(A5V(P->GetComponentTransform().TransformPosition(FVector(Q.Position))));N.Add(A5V(P->GetComponentTransform().TransformVectorNoScale(FVector(Q.Normal)).GetSafeNormal()));UV.Add(MakeShared<FJsonValueArray>(TArray<TSharedPtr<FJsonValue>>{MakeShared<FJsonValueNumber>(Q.UV0.X),MakeShared<FJsonValueNumber>(Q.UV0.Y)}));if(bPhase6 && Bridge && FPlatformTime::Seconds()-Heartbeat>.05){Bridge->TickFrozenBridge();Heartbeat=FPlatformTime::Seconds();} }
        for(uint32 I:S->ProcIndexBuffer) T.Add(MakeShared<FJsonValueNumber>(I));
        O->SetArrayField(TEXT("vertices_cm"),V);O->SetArrayField(TEXT("shading_vertex_normals"),N);O->SetArrayField(TEXT("triangles"),T);O->SetArrayField(TEXT("uvs"),UV);Objects.Add(MakeShared<FJsonValueObject>(O));
    };
    Add(TissueMesh,AnatomyGallbladderId,TEXT("gallbladder_physical_boundary"));Add(AnatomyAttachment,500,TEXT("hepatic_attachment_visual_membrane"));
    for(int I=0;I<AnatomyMeshes.Num();++I) Add(AnatomyMeshes[I],AnatomyIds[I],AnatomyNames[I]);
    for(int I=0;I<InstrumentDetailMeshes.Num();++I) Add(InstrumentDetailMeshes[I],1000+I,InstrumentDetailMeshes[I]->GetName());
    for(int I=0;I<AnatomyRods.Num();++I) Add(AnatomyRods[I],2000+I,AnatomyRods[I]->GetName());
    Root->SetArrayField(TEXT("objects"),Objects);return Root;
}

bool ATrainingScene::CapturePhase5Stereo(const FString& Sequence,int32 Frame)
{
    if(!Bridge || !Bridge->IsHealthy() || !Bridge->GetAcceptedState().IsValid()) return false;
    bPhase5CapturePrevious=true;if(bPhase6)bResumeSnapshot=true;Bridge->TickFrozenBridge();
    constexpr int W=640,H=512; const FString Dir=FPaths::Combine(Phase5Directory,TEXT("dataset"),Sequence,FString::Printf(TEXT("%04d"),Frame));
    IFileManager::Get().MakeDirectory(*Dir,true);
    if(!AnatomyCapture)
    {
        AnatomyCapture=NewObject<USceneCaptureComponent2D>(this,TEXT("AnatomyStereoCapture"));AnatomyCapture->SetupAttachment(SceneRoot);AnatomyCapture->bCaptureEveryFrame=false;AnatomyCapture->bCaptureOnMovement=false;AnatomyCapture->bAlwaysPersistRenderingState=bPhase6;
        AnatomyCapture->bUseRayTracingIfEnabled=bPhase6;
        AnatomyCapture->PrimitiveRenderMode=ESceneCapturePrimitiveRenderMode::PRM_UseShowOnlyList;
        AnatomyCapture->ShowOnlyComponent(TissueMesh);AnatomyCapture->ShowOnlyComponent(AnatomyAttachment);
        for(auto P:AnatomyMeshes) AnatomyCapture->ShowOnlyComponent(P);
        for(auto P:Phase6StaticMeshes) AnatomyCapture->ShowOnlyComponent(P);
        for(auto P:InstrumentDetailMeshes) AnatomyCapture->ShowOnlyComponent(P);
        for(auto P:AnatomyRods) AnatomyCapture->ShowOnlyComponent(P);
        AnatomyCapture->ShowFlags.SetAntiAliasing(false);AnatomyCapture->ShowFlags.SetMotionBlur(false);AnatomyCapture->ShowFlags.SetTemporalAA(false);
        AnatomyCapture->bOverride_CustomNearClippingPlane=true;AnatomyCapture->CustomNearClippingPlane=.15;
        AnatomyCapture->PostProcessSettings=Camera->PostProcessSettings;AnatomyCapture->PostProcessBlendWeight=1;
        AnatomyCapture->RegisterComponent();
        AnatomyRGBTarget=NewObject<UTextureRenderTarget2D>(this);AnatomyRGBTarget->ClearColor=FLinearColor::Black;AnatomyRGBTarget->InitCustomFormat(W,H,PF_B8G8R8A8,false);AnatomyRGBTarget->UpdateResourceImmediate(true);
        AnatomyDepthTarget=NewObject<UTextureRenderTarget2D>(this);AnatomyDepthTarget->ClearColor=FLinearColor::Black;AnatomyDepthTarget->InitCustomFormat(W,H,PF_A32B32G32R32F,true);AnatomyDepthTarget->UpdateResourceImmediate(true);
    }
    auto Geometry=BuildPhase5RenderGeometry();if(!(bPhase6?SavePhase6Json(FPaths::Combine(Dir,TEXT("geometry.json")),Geometry):A5Save(FPaths::Combine(Dir,TEXT("geometry.json")),Geometry))) return false;
    TArray<A5Triangle> Tris;
    for(const auto& Value:Geometry->GetArrayField(TEXT("objects")))
    {
        const auto O=Value->AsObject();const auto& V=O->GetArrayField(TEXT("vertices_cm"));const auto& F=O->GetArrayField(TEXT("triangles"));const int32 Id=int32(O->GetNumberField(TEXT("object_id")));
        for(int32 I=0;I+2<F.Num();I+=3) { A5Triangle T;T.Id=Id;for(int J=0;J<3;++J) T.P[J]=A5Read(V[int32(F[I+J]->AsNumber())]);Tris.Add(T); }
    }
    auto Record=MakeShared<FJsonObject>();Record->SetStringField(TEXT("schema"),TEXT("endoforge.phase5.stereo.v1"));Record->SetStringField(TEXT("sequence"),Sequence);Record->SetNumberField(TEXT("frame"),Frame);Record->SetObjectField(TEXT("native_state"),Bridge->GetAcceptedState());Record->SetStringField(TEXT("geometry"),TEXT("geometry.json"));Record->SetNumberField(TEXT("baseline_mm"),5);Record->SetNumberField(TEXT("dynamic_object_id"),AnatomyGallbladderId);Record->SetStringField(TEXT("visual_manifest"),TEXT("../../visual-manifest.json"));Record->SetStringField(TEXT("visual_manifest_sha1"),AnatomyVisualFingerprint);Record->SetStringField(TEXT("normal_winding_convention"),TEXT("ue_clockwise_cross_C_A_B_A"));Record->SetStringField(TEXT("pixel_convention"),TEXT("top-left origin; pixel centers x+0.5,y+0.5; no distortion; no AA; global shutter frozen displayed state"));Record->SetStringField(TEXT("normals"),TEXT("unit world front-face geometric normals = normalize(cross(C-A,B-A)) for UE clockwise triangles; distinct from shader normals"));
    Record->SetBoolField(TEXT("capture_hardware_ray_tracing_requested"),AnatomyCapture->bUseRayTracingIfEnabled);
    Record->SetNumberField(TEXT("capture_warmup_frames"),bPhase6?12:1);
    Record->SetStringField(TEXT("temporal_history"),bPhase6?TEXT("Persistent Lumen lighting history; 12 captures at each fixed eye pose, same frozen geometry. RGB has no AA or motion blur; geometric labels are exact current triangles, not temporally averaged."):TEXT("Single capture; no persistent history."));
    const FRotator Rotation=Camera->GetComponentRotation();const FRotationMatrix R(Rotation);const FVector Forward=R.GetUnitAxis(EAxis::X),Right=R.GetUnitAxis(EAxis::Y),Up=R.GetUnitAxis(EAxis::Z);const double Fov=Camera->FieldOfView,Focal=W/(2*FMath::Tan(FMath::DegreesToRadians(Fov*.5)));
    TArray<TSharedPtr<FJsonValue>> Eyes;bool All=true;
    for(int Eye=0;Eye<2;++Eye)
    {
        const FString Name=Eye?TEXT("right"):TEXT("left");const FString EDir=FPaths::Combine(Dir,Name);IFileManager::Get().MakeDirectory(*EDir,true);
        const FVector Pos=Camera->GetComponentLocation()+Right*(Eye?.25:-.25);AnatomyCapture->SetWorldLocationAndRotation(Pos,Rotation);AnatomyCapture->FOVAngle=Fov;
        AnatomyCapture->TextureTarget=AnatomyRGBTarget;AnatomyCapture->CaptureSource=SCS_FinalColorLDR;
        for(int Warm=0;Warm<(bPhase6?12:1);++Warm){AnatomyCapture->CaptureScene();FlushRenderingCommands();Bridge->TickFrozenBridge();}
        TArray<FColor> Pixels;
        All &= AnatomyRGBTarget->GameThread_GetRenderTargetResource()->ReadPixels(Pixels);
        if(Pixels.Num()!=W*H) return false;
        Bridge->TickFrozenBridge();
        TArray<uint8> PNG;FImageUtils::CompressImageArray(W,H,Pixels,PNG);All &= FFileHelper::SaveArrayToFile(PNG,*FPaths::Combine(EDir,TEXT("rgb.png")));
        AnatomyCapture->TextureTarget=AnatomyDepthTarget;AnatomyCapture->CaptureSource=SCS_SceneDepth;AnatomyCapture->CaptureScene();FlushRenderingCommands();TArray<FLinearColor> DepthRGBA;
        FReadSurfaceDataFlags Flags(RCM_MinMax);Flags.SetLinearToGamma(false);All &= AnatomyDepthTarget->GameThread_GetRenderTargetResource()->ReadLinearColorPixels(DepthRGBA,Flags);
        if(DepthRGBA.Num()!=W*H) return false;
        TArray<float> Depth,GeoDepth,Normal;TArray<int32> Ids;TArray<uint8> Valid;Depth.SetNumUninitialized(W*H);GeoDepth.Init(TNumericLimits<float>::Max(),W*H);Normal.Init(0,W*H*3);Ids.Init(0,W*H);Valid.Init(0,W*H);
        for(int I=0;I<W*H;++I) Depth[I]=DepthRGBA[I].R*10;
        TArray<A5Triangle> VisibleTriangles;
        for(const auto& T:Tris)
        {
            TArray<FVector> Polygon{T.P[0],T.P[1],T.P[2]},Clipped;
            for(int I=0;I<Polygon.Num();++I)
            {
                const FVector A=Polygon[I],B=Polygon[(I+1)%Polygon.Num()];const double DA=FVector::DotProduct(A-Pos,Forward)-.15,DB=FVector::DotProduct(B-Pos,Forward)-.15;
                if(DA>=0)Clipped.Add(A);
                if((DA>=0)!=(DB>=0))Clipped.Add(A+(B-A)*(DA/(DA-DB)));
            }
            for(int I=1;I+1<Clipped.Num();++I){A5Triangle C;C.Id=T.Id;C.P[0]=Clipped[0];C.P[1]=Clipped[I];C.P[2]=Clipped[I+1];VisibleTriangles.Add(C);}
        }
        double LastHeartbeat=FPlatformTime::Seconds();
        for(const auto& T:VisibleTriangles)
        {
            if(FPlatformTime::Seconds()-LastHeartbeat>.05) { Bridge->TickFrozenBridge(); LastHeartbeat=FPlatformTime::Seconds(); }
            double X[3],Y[3],Z[3];bool Good=true;
            for(int J=0;J<3;++J) { const FVector D=T.P[J]-Pos;Z[J]=FVector::DotProduct(D,Forward);if(Z[J]<.14999) { Good=false;break; }X[J]=W*.5+Focal*FVector::DotProduct(D,Right)/Z[J];Y[J]=H*.5-Focal*FVector::DotProduct(D,Up)/Z[J]; }
            if(!Good) continue;
            const double Den=(Y[1]-Y[2])*(X[0]-X[2])+(X[2]-X[1])*(Y[0]-Y[2]);if(FMath::Abs(Den)<1e-10) continue;
            const int MinX=FMath::Clamp(FMath::FloorToInt(FMath::Min3(X[0],X[1],X[2])),0,W-1),MaxX=FMath::Clamp(FMath::CeilToInt(FMath::Max3(X[0],X[1],X[2])),0,W-1);
            const int MinY=FMath::Clamp(FMath::FloorToInt(FMath::Min3(Y[0],Y[1],Y[2])),0,H-1),MaxY=FMath::Clamp(FMath::CeilToInt(FMath::Max3(Y[0],Y[1],Y[2])),0,H-1);
            const FVector N=FVector::CrossProduct(T.P[2]-T.P[0],T.P[1]-T.P[0]).GetSafeNormal(1e-24);
            for(int Yp=MinY;Yp<=MaxY;++Yp) for(int Xp=MinX;Xp<=MaxX;++Xp)
            {
                const double A=((Y[1]-Y[2])*(Xp+.5-X[2])+(X[2]-X[1])*(Yp+.5-Y[2]))/Den;
                const double B=((Y[2]-Y[0])*(Xp+.5-X[2])+(X[0]-X[2])*(Yp+.5-Y[2]))/Den,C=1-A-B;
                if(FMath::Min3(A,B,C)<-1e-9) continue;const float Zmm=10/(A/Z[0]+B/Z[1]+C/Z[2]);const int I=Yp*W+Xp;
                if(Zmm<GeoDepth[I]) { GeoDepth[I]=Zmm;Ids[I]=T.Id;Normal[I*3]=N.X;Normal[I*3+1]=N.Y;Normal[I*3+2]=N.Z; }
            }
        }
        double SumSq=0,MaxError=0;int Count=0;TArray<float> Errors;
        for(int Y=1;Y<H-1;++Y) for(int X=1;X<W-1;++X)
        {
            const int I=Y*W+X;const bool Interior=Ids[I]>0 && Ids[I-1]==Ids[I] && Ids[I+1]==Ids[I] && Ids[I-W]==Ids[I] && Ids[I+W]==Ids[I] && FMath::Abs(GeoDepth[I-1]-GeoDepth[I+1])<2 && FMath::Abs(GeoDepth[I-W]-GeoDepth[I+W])<2;
            if(Interior && FMath::IsFinite(Depth[I]) && Depth[I]>0 && Depth[I]<5000)
            { Valid[I]=1;double E=FMath::Abs(Depth[I]-GeoDepth[I]);SumSq+=E*E;MaxError=FMath::Max(MaxError,E);Errors.Add(E);++Count; }
        }
        for(int I=0;I<W*H;++I) if(!Ids[I]) GeoDepth[I]=0;
        All &= A5Npy(FPaths::Combine(EDir,TEXT("depth_mm.npy")),Depth.GetData(),Depth.Num()*sizeof(float),TEXT("<f4"),TEXT("512, 640"));
        All &= A5Npy(FPaths::Combine(EDir,TEXT("geometry_depth_mm.npy")),GeoDepth.GetData(),GeoDepth.Num()*sizeof(float),TEXT("<f4"),TEXT("512, 640"));
        All &= A5Npy(FPaths::Combine(EDir,TEXT("geometric_normal_world.npy")),Normal.GetData(),Normal.Num()*sizeof(float),TEXT("<f4"),TEXT("512, 640, 3"));
        All &= A5Npy(FPaths::Combine(EDir,TEXT("object_id.npy")),Ids.GetData(),Ids.Num()*sizeof(int32),TEXT("<i4"),TEXT("512, 640"));
        All &= A5Npy(FPaths::Combine(EDir,TEXT("valid.npy")),Valid.GetData(),Valid.Num(),TEXT("|u1"),TEXT("512, 640"));
        auto E=MakeShared<FJsonObject>();E->SetStringField(TEXT("eye"),Name);E->SetNumberField(TEXT("width"),W);E->SetNumberField(TEXT("height"),H);E->SetNumberField(TEXT("fx_px"),Focal);E->SetNumberField(TEXT("fy_px"),Focal);E->SetNumberField(TEXT("cx_px"),W*.5);E->SetNumberField(TEXT("cy_px"),H*.5);E->SetField(TEXT("position_cm"),A5V(Pos));E->SetField(TEXT("forward"),A5V(Forward));E->SetField(TEXT("right"),A5V(Right));E->SetField(TEXT("up"),A5V(Up));E->SetNumberField(TEXT("valid_pixels"),Count);E->SetNumberField(TEXT("gpu_vs_geometry_depth_rms_mm"),Count?FMath::Sqrt(SumSq/Count):1e9);E->SetNumberField(TEXT("gpu_vs_geometry_depth_max_mm"),MaxError);Eyes.Add(MakeShared<FJsonValueObject>(E));
        Errors.Sort();const double P99=Errors.Num()?Errors[FMath::Clamp(FMath::FloorToInt(.99*Errors.Num()),0,Errors.Num()-1)]:1e9;E->SetNumberField(TEXT("gpu_vs_geometry_depth_p99_mm"),P99);
        All &= Count>1000 && FMath::Sqrt(SumSq/FMath::Max(1,Count))<=.1 && P99<=.15;
    }
    Record->SetArrayField(TEXT("eyes"),Eyes);Record->SetBoolField(TEXT("capture_complete"),All);All &= A5Save(FPaths::Combine(Dir,TEXT("frame.json")),Record);++Phase5DatasetFrames;
    if(bPhase6)bResumeSnapshot=true;
    return All;
}

void ATrainingScene::AdvancePhase5Test(int32 Stage)
{
    if(bPhase6)
    {
        if(Stage==5)bPhase6RightApproachSampled=false;
        if(Stage==2)CapturePhase6Review(TEXT("phase6-workspace"));
        if(Stage==4){CapturePhase6Review(TEXT("phase6-jaw-contact"),true);CapturePhase6Review(TEXT("phase6-organ-closeup"),true);}
        if(Stage==8)CapturePhase6Review(TEXT("phase6-dual-traction"));
    }
    StopTestMotion();for(const FKey& K:{EKeys::F,EKeys::C,EKeys::Two,EKeys::Three,EKeys::F5,EKeys::F6,EKeys::F7,EKeys::R})SetTestKey(K,false);
    Phase5Stage=Stage;Phase5Ticks=0;Phase5StageElapsed=0;Phase5Dwell=0;
    UE_LOG(LogTemp,Display,TEXT("LAP_PHASE5_STAGE %d"),Stage);
}

void ATrainingScene::UpdatePhase5Test(float Dt)
{
    if(bPhase5Finished) return;Phase5Elapsed+=Dt;Phase5StageElapsed+=Dt;++Phase5Ticks;
    if(!AnatomyError.IsEmpty()) { FinishPhase5Test(AnatomyError);return; }
    if(Phase5Elapsed>300) { FinishPhase5Test(TEXT("Phase5 input exercise timed out"));return; }
    if(!Bridge || !Bridge->IsConnected() || !bPhase5HomeAdopted) { if(Phase5Elapsed>30)FinishPhase5Test(TEXT("Phase5 physics did not connect"));return; }
    if(!Bridge->IsHealthy() || Bridge->GetSafetyStopCount()>0) { FinishPhase5Test(TEXT("Native safety stop during input exercise"));return; }
    Phase5PeakDisplacementMm=FMath::Max(Phase5PeakDisplacementMm,double(Bridge->GetMaxDisplacementCm()*10));
    for(int T=0;T<2;++T) if(const auto* S=Bridge->GetToolState(T)) Phase5PeakPenetrationMm=FMath::Max(Phase5PeakPenetrationMm,double(S->PenetrationMm));
    const auto* L=Bridge->GetToolState(0);const auto* R=Bridge->GetToolState(1);
    // A single grasp must remain physical while the second instrument approaches.
    // Report this failure at its actual stage instead of calling it dual traction.
    if(bPhase6 && bPhase5Grip[0] && Phase5Stage>=4 && Phase5Stage<=6 && (!L || !L->bGrasping))
    { FinishPhase5Test(TEXT("Left grasper lost physical contact before coordinated dual traction"));return; }
    // Retention is mandatory throughout coordinated traction, including states received
    // after each frozen capture. Initial simultaneous contact cannot satisfy this gate.
    if((Phase5Stage==7 || (Phase5Stage>=17&&Phase5Stage<=21)) &&
        (!L || !R || !L->bGrasping || !R->bGrasping))
    { FinishPhase5Test(TEXT("A grasper slipped during coordinated dual traction"));return; }
    auto CaptureTo=[&](int Sequence,int Count)
    {
        if(FParse::Param(FCommandLine::Get(),TEXT("LapPhase5SkipDataset"))) return true;
        if(Phase5SequenceCounts[Sequence]>=Count) return true;
        if(Bridge->GetStepIndex()!=Phase5LastCapturedStep)
        {
            StopTestMotion();
            if(!CapturePhase5Stereo(Sequence?TEXT("bimanual_traction"):TEXT("left_traction"),Phase5SequenceCounts[Sequence]++)) Phase5Failures.AddUnique(TEXT("Stereo capture failed"));
            Phase5LastCapturedStep=Bridge->GetStepIndex();
            // Advance only after the accepted state has caught up. Issuing an
            // F key in the same tick as a long export sees stale connectivity.
            if(bPhase6)return false;
        }
        return Phase5SequenceCounts[Sequence]>=Count;
    };
    auto AdditionalDisplacementMm=[&](const TArray<FVector>& Baseline)
    {
        TArray<FVector> Current;TArray<int32> Faces;double Maximum=0;
        if(!Bridge->GetSurface(Current,Faces)||Current.Num()!=Baseline.Num()||Baseline.IsEmpty())return -1.0;
        for(int32 I=0;I<Current.Num();++I)Maximum=FMath::Max(Maximum,FVector::Distance(Current[I],Baseline[I])*10);
        return Maximum;
    };
    auto ReadyApproachComplete=[&](int32 Index)
    {
        const auto* Actual=Bridge->GetToolState(Index);
        return Actual && !Phase6SampledApproachWaypoints[Index].IsEmpty() &&
            !Phase6Interaction.Tools[Index].bPositionTarget &&
            FVector::Distance(Actual->ActualTipCm,Phase6SampledReadyTargets[Index])<=.012 &&
            FMath::Abs(FMath::FindDeltaAngleDegrees(Actual->RollDeg,Phase6ReadyRolls[Index]))<=.1;
    };
    switch(Phase5Stage)
    {
    case 0:
        if(Phase5StageElapsed>.7) { SetTestKey(EKeys::F5,true);AdvancePhase5Test(1);SetTestKey(EKeys::F5,true); }break;
    case 1:
        if(Bridge->GetSessionMode()==TEXT("recording") && Bridge->HasAcknowledgedReset() && CaptureTo(0,2)) { bPhase5Record=true;AdvancePhase5Test(2);if(bPhase6)SetTestKey(EKeys::Two,true); }break;
    case 2:
        if((bPhase6?ReadyApproachComplete(0):DriveTestTo(Phase5Targets[0])) && CaptureTo(0,4) && CaptureTo(1,2)) { AdvancePhase5Test(3);SetTestKey(EKeys::F,true); }break;
    case 3:
        if(L && L->bGrasping && CaptureTo(0,6) && CaptureTo(1,4)) { bPhase5Grip[0]=true;TArray<int32> Faces;Bridge->GetSurface(Phase5LeftBaselineVertices,Faces);Phase5LiftTargets[0]=(bPhase6?ActualTips[0]:ToolTips[0])+FVector(0,0,.1);AdvancePhase5Test(4); }
        else if(Phase5StageElapsed>12) FinishPhase5Test(TEXT("Left grasper did not hold"));break;
    case 4:
        if(DriveTestTo(Phase5LiftTargets[0]) && CaptureTo(0,8)) { Phase5LeftTractionMm=AdditionalDisplacementMm(Phase5LeftBaselineVertices);bPhase5Traction=L&&L->bGrasping&&Phase5LeftTractionMm>.5;AdvancePhase5Test(5);SetTestKey(EKeys::C,true); }break;
    case 5:
        if(ActiveTool==1)
        {
            if(bPhase6 && !bPhase6RightApproachSampled)
            {
                SetTestKey(EKeys::Three,true);bPhase6RightApproachSampled=true;break;
            }
            if(bPhase6?ReadyApproachComplete(1):DriveTestTo(Phase5Targets[1])) { AdvancePhase5Test(6);SetTestKey(EKeys::F,true); }
        }break;
    case 6:
        if(R && R->bGrasping && CaptureTo(1,6))
        {
            bPhase5Grip[1]=true;bPhase5Dual=L&&L->bGrasping;
            TArray<int32> Faces;Bridge->GetSurface(Phase5DualBaselineVertices,Faces);
            if(bPhase6)for(int32 I=0;I<2;++I)Phase6DualBaselineTips[I]=ActualTips[I];
            // Match the native two-millimetre, right-then-left dual exercise.
            // Each target is anchored to the accepted dual-grasp baseline.
            Phase5LiftTargets[1]=(bPhase6?Phase6DualBaselineTips[1]:ToolTips[1])+FVector(0,0,bPhase6?.2:.1);
            AdvancePhase5Test(7);
        }
        else if(Phase5StageElapsed>12) FinishPhase5Test(TEXT("Right grasper did not hold"));break;
    case 7:
        if(DriveTestTo(Phase5LiftTargets[1])) { AdvancePhase5Test(17);SetTestKey(EKeys::C,true); }break;
    case 17:
        if(ActiveTool==0) { Phase5LiftTargets[0]=(bPhase6?Phase6DualBaselineTips[0]:ToolTips[0])+FVector(0,0,bPhase6?.2:.1);AdvancePhase5Test(18); }break;
    case 18:
        if(DriveTestTo(Phase5LiftTargets[0]))
        {
            if(bPhase6)
            {
                if(CaptureTo(1,8)){Phase5DualCaptureStep=Bridge->GetStepIndex();AdvancePhase5Test(21);}
            }
            else {AdvancePhase5Test(19);SetTestKey(EKeys::C,true);}
        }break;
    case 19:
        if(ActiveTool==1) { Phase5LiftTargets[1]=(bPhase6?ActualTips[1]:ToolTips[1])+FVector(0,0,.1);AdvancePhase5Test(20); }break;
    case 20:
        if(DriveTestTo(Phase5LiftTargets[1]) && CaptureTo(1,8)) { Phase5DualCaptureStep=Bridge->GetStepIndex();AdvancePhase5Test(21); }break;
    case 21:
        if(Bridge->GetStepIndex()>Phase5DualCaptureStep && Phase5StageElapsed>.05)
        {
            Phase5DualTractionMm=AdditionalDisplacementMm(Phase5DualBaselineVertices);
            bPhase5DualTractionRetained=L&&R&&L->bGrasping&&R->bGrasping&&Phase5DualTractionMm>=1.5;
            if(bPhase6)
            {
                for(int32 I=0;I<2;++I)
                {
                    Phase6DualTractionDeltas[I]=ActualTips[I]-Phase6DualBaselineTips[I];
                    bPhase5DualTractionRetained&=FVector::Distance(Phase6DualTractionDeltas[I],FVector(0,0,.2))<=.012;
                }
            }
            if(!bPhase5DualTractionRetained) { FinishPhase5Test(TEXT("Dual traction did not retain both grasps and add at least 1.5 mm displacement from the dual-grasp baseline"));break; }
            if(bPhase6 && ActiveTool!=1)
            {
                // The release sequence starts with the right instrument.
                SetTestKey(EKeys::C,true);break;
            }
            AdvancePhase5Test(8);SetTestKey(EKeys::F,true);
        }break;
    case 8:
        if(R && !R->bGrasping && R->JawOpenFraction>.9 && CaptureTo(0,10) && CaptureTo(1,10)) { AdvancePhase5Test(9);SetTestKey(EKeys::C,true); }break;
    case 9:
        if(ActiveTool==0) { AdvancePhase5Test(10);SetTestKey(EKeys::Two,true); }break;
    case 10:
        if(L&&R&&!L->bGrasping&&!R->bGrasping&&L->JawOpenFraction>.9&&R->JawOpenFraction>.9 && CaptureTo(0,12) && CaptureTo(1,12)) { bPhase5Release=true;AdvancePhase5Test(11);SetTestKey(EKeys::F5,true); }break;
    case 11:
        if(Bridge->GetSessionMode()==TEXT("idle") && !Bridge->HasPendingSessionAction()) { Phase5RecordLength=Bridge->GetRecordedSteps();AdvancePhase5Test(12);SetTestKey(EKeys::F6,true); }break;
    case 12:
        if(Bridge->GetSessionMode()==TEXT("replaying")) bPhase5Replay=true;
        if(Bridge->GetSessionMode()==TEXT("replay_complete")) { bPhase5ReplayDone=true;AdvancePhase5Test(13);SetTestKey(EKeys::F7,true); }break;
    case 13:
        if(Phase5StageElapsed>2 && Phase4SnapshotCount>0 && !bSnapshotFrozen) { AdvancePhase5Test(14);SetTestKey(EKeys::F6,true); }break;
    case 14:
        if(!Bridge->IsReplayLocked()) AdvancePhase5Test(15);break;
    case 15:
        if(Phase5StageElapsed>.5) FinishPhase5Test();break;
    }

}

void ATrainingScene::FinishPhase5Test(const FString& Failure)
{
    if(bPhase5Finished)return;bPhase5Finished=true;StopTestMotion();for(const FName& Name:TArray<FName>(TestHeldKeys.Array()))SetTestKey(FKey(Name),false);
    if(!Failure.IsEmpty())Phase5Failures.AddUnique(Failure);
    FlushPresentedStates();
    for(const FString& SnapshotOrRecordFailure:Phase4Failures)Phase5Failures.AddUnique(SnapshotOrRecordFailure);
    auto O=MakeShared<FJsonObject>();O->SetStringField(TEXT("schema"),TEXT("endoforge.phase5.input_test.v1"));O->SetNumberField(TEXT("phase"),bPhase6?6:5);auto Checks=MakeShared<FJsonObject>();
    Checks->SetBoolField(TEXT("anatomy_assets_loaded"),AnatomyError.IsEmpty()&&AnatomyMeshes.Num()>=3);
    Checks->SetBoolField(TEXT("left_contact_grip"),bPhase5Grip[0]);Checks->SetBoolField(TEXT("right_contact_grip"),bPhase5Grip[1]);Checks->SetBoolField(TEXT("traction_deforms"),bPhase5Traction);Checks->SetBoolField(TEXT("dual_hold"),bPhase5Dual);Checks->SetBoolField(TEXT("release_both"),bPhase5Release);Checks->SetBoolField(TEXT("preset_releases_latched_left"),bPhase5Release&&!Phase5Latches[0]);
    Checks->SetBoolField(TEXT("dual_traction_retained"),bPhase5DualTractionRetained);
    O->SetNumberField(TEXT("dual_traction_displacement_mm"),Phase5DualTractionMm);
    if(bPhase6)
    {
        TArray<TSharedPtr<FJsonValue>> ActualDeltas;
        for(const FVector& Delta:Phase6DualTractionDeltas)ActualDeltas.Add(A5V(Delta*10));
        O->SetArrayField(TEXT("dual_instrument_displacements_mm"),ActualDeltas);
        O->SetStringField(TEXT("dual_instrument_displacement_reference"),TEXT("Accepted tips at the same dual-grasp baseline as the tissue; ordinary Ctrl+wheel 0.2 mm pulses with applied-command and settled-position acknowledgement; +2 mm world Z per instrument, right then left; unchanged 0.12 mm endpoint tolerance"));
    }
    O->SetNumberField(TEXT("left_traction_displacement_mm"),Phase5LeftTractionMm);
    O->SetStringField(TEXT("traction_displacement_reference"),TEXT("maximum per-node distance from the accepted immediately post-grasp baseline, before the associated traction motion; not displacement from rest"));
    if(bPhase6)O->SetArrayField(TEXT("material_bound_ready_targets"),Phase6ReadyTargetSamples);
    Checks->SetBoolField(TEXT("recorded"),bPhase5Record&&Phase5RecordLength>0);Checks->SetBoolField(TEXT("replay_completed"),bPhase5Replay&&bPhase5ReplayDone);Checks->SetBoolField(TEXT("snapshot"),Phase4SnapshotCount>0&&Phase4Failures.IsEmpty());Checks->SetBoolField(TEXT("stereo_frames"),Phase5DatasetFrames>=24);Checks->SetBoolField(TEXT("stereo_alignment"),Phase5DatasetFrames>=24&&!Phase5Failures.Contains(TEXT("Stereo capture failed")));Checks->SetBoolField(TEXT("healthy"),Bridge&&Bridge->IsHealthy()&&Bridge->GetSafetyStopCount()==0);Checks->SetBoolField(TEXT("penetration_bound"),Phase5PeakPenetrationMm<=.15);
    if(bPhase6) WritePhase6Runtime();
    bool Passed=Phase5Failures.IsEmpty();for(const auto& Pair:Checks->Values)Passed&=Pair.Value->AsBool();
    O->SetObjectField(TEXT("checks"),Checks);O->SetBoolField(TEXT("passed"),Passed);O->SetNumberField(TEXT("peak_displacement_mm"),Phase5PeakDisplacementMm);O->SetNumberField(TEXT("peak_node_penetration_mm"),Phase5PeakPenetrationMm);O->SetNumberField(TEXT("stereo_frames"),Phase5DatasetFrames);O->SetStringField(TEXT("model_id"),AnatomyModelId);O->SetStringField(TEXT("model_version"),AnatomyModelVersion);
    TArray<TSharedPtr<FJsonValue>> Errors;for(const auto& E:Phase5Failures)Errors.Add(MakeShared<FJsonValueString>(E));O->SetArrayField(TEXT("errors"),Errors);
    Phase5FrameTimes.Sort();auto Performance=MakeShared<FJsonObject>();
    double Total=0;for(float T:Phase5FrameTimes)Total+=T;
    Performance->SetNumberField(TEXT("interactive_frames_measured"),Phase5FrameTimes.Num());Performance->SetNumberField(TEXT("mean_fps"),Total>0?Phase5FrameTimes.Num()/Total:0);
    const double P95=Phase5FrameTimes.Num()?Phase5FrameTimes[FMath::Clamp(FMath::FloorToInt(.95*Phase5FrameTimes.Num()),0,Phase5FrameTimes.Num()-1)]:1;
    Performance->SetNumberField(TEXT("p95_frame_ms"),P95*1000);Performance->SetNumberField(TEXT("p5_fps"),1/P95);
    Performance->SetNumberField(TEXT("native_sim_time_per_wall_time"),Phase5MeasuredWall>0?Phase5MeasuredNative/Phase5MeasuredWall:0);
    Performance->SetStringField(TEXT("scope"),TEXT("interactive UE tick samples; blocking dataset export, snapshot freeze and immediate following tick excluded; no fixed-FPS assumption"));O->SetObjectField(TEXT("performance"),Performance);
    A5Save(FPaths::Combine(Phase5Directory,TEXT("phase5-input-test.json")),O);FlushPresentedStates();
    UE_LOG(LogTemp,Display,TEXT("LAP_PHASE5_TEST %s %s"),Passed?TEXT("PASS"):TEXT("FAIL"),*Failure);
    if(bAutoExit) FPlatformMisc::RequestExit(false);
}
