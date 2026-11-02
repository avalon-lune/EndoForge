#include "Phase7AttachmentGeometry.h"
#include "Algo/Reverse.h"
#include "Dom/JsonObject.h"

namespace
{
FVector Curve(const FVector& P0,const FVector& P1,const FVector& P2,const FVector& P3,double T)
{
    if(T==0)return P1;if(T==1)return P2;
    return (P1*2+(P2-P0)*T+(P0*2-P1*5+P2*4-P3)*T*T+(-P0+P1*3-P2*3+P3)*T*T*T)*.5;
}
}

bool Phase7AttachmentGeometry::Build(const TArray<int32>& Ids,const TArray<FVector>& Pairs,
    const TArray<FIntPoint>& Edges,FTrainingRenderMesh& M,FBinding& Binding,FString& Error)
{
    M=FTrainingRenderMesh();Binding=FBinding();Error.Reset();
    auto Fail=[&](const TCHAR* Reason){Error=Reason;return false;};
    if(Ids.Num()<3||Pairs.Num()!=Ids.Num()*2||Edges.Num()<3)return Fail(TEXT("Invalid native attachment input counts"));
    TMap<int32,int32> Index;TMap<int32,TArray<int32>> Neighbours;
    for(int I=0;I<Ids.Num();++I)
    {
        if(Index.Contains(Ids[I])||Pairs[I*2].ContainsNaN()||Pairs[I*2+1].ContainsNaN())return Fail(TEXT("Duplicate attachment identity or nonfinite endpoint"));
        Index.Add(Ids[I],I);
    }
    for(const auto& E:Edges)
    {
        if(E.X==E.Y||!Index.Contains(E.X)||!Index.Contains(E.Y)||Neighbours.FindOrAdd(E.X).Contains(E.Y))return Fail(TEXT("Invalid or duplicate attachment boundary edge"));
        Neighbours.FindOrAdd(E.X).Add(E.Y);Neighbours.FindOrAdd(E.Y).Add(E.X);
    }
    int Start=MAX_int32;
    for(auto& Entry:Neighbours)
    {
        if(Entry.Value.Num()!=2)return Fail(TEXT("Attachment boundary must be a degree-two loop"));
        Entry.Value.Sort();Start=FMath::Min(Start,Entry.Key);
    }
    TArray<int32> Loop;int Previous=INDEX_NONE,Current=Start;
    do
    {
        if(Loop.Contains(Current)||Loop.Num()>Edges.Num())return Fail(TEXT("Attachment boundary repeats before closing"));
        Loop.Add(Current);const auto& N=Neighbours[Current];const int Next=N[0]==Previous?N[1]:N[0];Previous=Current;Current=Next;
    }while(Current!=Start);
    if(Loop.Num()!=Edges.Num()||Loop.Num()!=Neighbours.Num())return Fail(TEXT("Attachment boundary contains disconnected loops"));
    FVector Centre=FVector::ZeroVector;
    for(int Id:Loop)Centre+=(Pairs[Index[Id]*2]+Pairs[Index[Id]*2+1])*.5;
    Centre/=Loop.Num();double Orientation=0;
    for(int I=0;I<Loop.Num();++I)
    {
        const FVector A=Pairs[Index[Loop[I]]*2],B=Pairs[Index[Loop[(I+1)%Loop.Num()]]*2],D=Pairs[Index[Loop[I]]*2+1];
        Orientation+=FVector::DotProduct(FVector::CrossProduct(B-A,D-A),(A+B+D)/3-Centre);
    }
    if(Orientation<0)Algo::Reverse(Loop);
    Binding.ClosedBoundaryMaterialIds=Loop;
    for(int I=0;I<Loop.Num();++I)
    {
        const int A=Loop[I],B=Loop[(I+1)%Loop.Num()];
        Binding.OriginalEdgeDirections.Add(Edges.Contains(FIntPoint(A,B))?1:-1);
    }
    M.Positions=Pairs;
    for(int I=0;I<Pairs.Num();++I){Binding.VertexBindings.Add(FVector(-1,I/2,I%2));M.UV.Add(FVector2D(0,I%2));}
    const int Count=Loop.Num(),Columns=Count*AlongSubdivisions,Rows=SpanSubdivisions+1;
    TArray<double> Distance;Distance.Add(0);
    auto Point=[&](int Node,int Side){return Pairs[Index[Loop[(Node%Count+Count)%Count]]*2+Side];};
    for(int I=0;I<Count;++I)Distance.Add(Distance.Last()+FVector::Distance((Point(I,0)+Point(I,1))*.5,(Point(I+1,0)+Point(I+1,1))*.5));
    if(Distance.Last()<1e-8)return Fail(TEXT("Attachment boundary has no measurable perimeter"));
    TArray<int32> Grid;Grid.SetNum((Columns+1)*Rows);
    for(int Column=0;Column<=Columns;++Column)
    {
        const int Edge=FMath::Min(Column/AlongSubdivisions,Count-1);
        const double U=Column==Columns?1:double(Column%AlongSubdivisions)/AlongSubdivisions;
        const FVector A=Point(Edge,0),B=Point(Edge+1,0),C=Point(Edge+1,1),D=Point(Edge,1);
        const FVector Top=Curve(Point(Edge-1,0),A,B,Point(Edge+2,0),U);
        const FVector Bottom=Curve(Point(Edge-1,1),D,C,Point(Edge+2,1),U);
        for(int Row=0;Row<Rows;++Row)
        {
            const double V=double(Row)/SpanSubdivisions;
            // Preserve the actual input edge's old diagonal, even where loop
            // ordering reverses that edge. This matters for non-planar quads.
            const FVector Base=Binding.OriginalEdgeDirections[Edge]>0
                ?(V<=U?A*(1-U)+B*(U-V)+C*V:A*(1-V)+C*U+D*(V-U))
                :(U+V<=1?A*(1-U-V)+B*U+D*V:B*(1-V)+C*(U+V-1)+D*(1-U));
            FVector Delta=FMath::Lerp(Top,Bottom,V)-Base;
            if(Delta.Size()>MaximumOffsetCm)Delta=Delta.GetSafeNormal()*MaximumOffsetCm;
            Binding.MeasuredMaximumOffsetCm=FMath::Max(Binding.MeasuredMaximumOffsetCm,Delta.Size());
            int Vertex;
            if(Column<Columns&&Column%AlongSubdivisions==0&&(Row==0||Row==SpanSubdivisions))Vertex=Index[Loop[Edge]]*2+(Row==0?0:1);
            else{Vertex=M.Positions.Add(Base+Delta);M.UV.Add(FVector2D::ZeroVector);Binding.VertexBindings.Add(FVector(Edge,U,V));}
            M.UV[Vertex]=FVector2D(FMath::Lerp(Distance[Edge],Distance[Edge+1],U)/Distance.Last(),V);
            Grid[Column*Rows+Row]=Vertex;
        }
    }
    for(int Column=0;Column<Columns;++Column)for(int Row=0;Row<SpanSubdivisions;++Row)
    {
        const int A=Grid[Column*Rows+Row],B=Grid[(Column+1)*Rows+Row],C=Grid[(Column+1)*Rows+Row+1],D=Grid[Column*Rows+Row+1];
        const int Edge=Column/AlongSubdivisions;
        if(Binding.OriginalEdgeDirections[Edge]>0)M.Triangles.Append({A,B,C,A,C,D});
        else M.Triangles.Append({A,B,D,B,C,D});
        Binding.TrianglePatchIndices.Append({Edge,Edge});
    }
    for(int Row=0;Row<Rows;++Row)Binding.SeamVertexPairs.Add(FIntPoint(Grid[Row],Grid[Columns*Rows+Row]));
    for(int I=0;I<M.Triangles.Num();I+=3)
    {
        const FVector A=M.Positions[M.Triangles[I]],B=M.Positions[M.Triangles[I+1]],C=M.Positions[M.Triangles[I+2]];
        if(FVector::CrossProduct(B-A,C-A).SizeSquared()<1e-24)return Fail(TEXT("Attachment visual contains a degenerate triangle"));
    }
    return true;
}

TSharedRef<FJsonObject> Phase7AttachmentGeometry::ToJson(const FBinding& Binding,const TArray<FIntPoint>& Edges,int32 PairCount)
{
    auto O=MakeShared<FJsonObject>();O->SetStringField(TEXT("schema"),TEXT("endoforge.phase7.attachment_visual.v1"));
    O->SetStringField(TEXT("scope"),TEXT("Continuous bounded visual envelope of native attachment springs; not a membrane FEM or added collision geometry. All native endpoint pairs preserved as prefix vertices; actual displayed triangles exported as object500."));
    O->SetNumberField(TEXT("native_endpoint_prefix_count"),PairCount*2);
    O->SetNumberField(TEXT("along_subdivisions"),AlongSubdivisions);O->SetNumberField(TEXT("span_subdivisions"),SpanSubdivisions);
    O->SetNumberField(TEXT("max_offset_cm"),MaximumOffsetCm);O->SetNumberField(TEXT("measured_max_offset_cm"),Binding.MeasuredMaximumOffsetCm);
    O->SetStringField(TEXT("interpolation"),TEXT("uniform_catmull_rom_each_boundary_side_then_span_lerp_clamped_to_literal_original_edge_triangles"));
    O->SetStringField(TEXT("vertex_binding_semantics"),TEXT("[-1,native_pair_index,endpoint_index] or [ordered_boundary_edge_index,u,v]; duplicated UV seam positions coincide exactly"));
    auto Pair=[](int A,int B){return MakeShared<FJsonValueArray>(TArray<TSharedPtr<FJsonValue>>{MakeShared<FJsonValueNumber>(A),MakeShared<FJsonValueNumber>(B)});};
    TArray<TSharedPtr<FJsonValue>> Loop,Samples,Patches,Seam,Directions,OriginalEdges;
    for(int Id:Binding.ClosedBoundaryMaterialIds)Loop.Add(MakeShared<FJsonValueNumber>(Id));
    for(const auto& B:Binding.VertexBindings)Samples.Add(MakeShared<FJsonValueArray>(TArray<TSharedPtr<FJsonValue>>{MakeShared<FJsonValueNumber>(B.X),MakeShared<FJsonValueNumber>(B.Y),MakeShared<FJsonValueNumber>(B.Z)}));
    for(int Patch:Binding.TrianglePatchIndices)Patches.Add(MakeShared<FJsonValueNumber>(Patch));
    for(int Direction:Binding.OriginalEdgeDirections)Directions.Add(MakeShared<FJsonValueNumber>(Direction));
    for(const auto& E:Edges)OriginalEdges.Add(Pair(E.X,E.Y));
    for(const auto& S:Binding.SeamVertexPairs)Seam.Add(Pair(S.X,S.Y));
    O->SetArrayField(TEXT("closed_boundary_material_ids"),Loop);O->SetArrayField(TEXT("vertex_bindings"),Samples);O->SetArrayField(TEXT("triangle_patch_indices"),Patches);O->SetArrayField(TEXT("seam_vertex_pairs"),Seam);
    O->SetArrayField(TEXT("original_edge_directions"),Directions);O->SetArrayField(TEXT("original_boundary_edges"),OriginalEdges);
    return O;
}
