#include "TrainingHUD.h"
#include "TrainingScene.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
void ATrainingHUD::Label(const FString& Text,float X,float Y,float Scale,const FLinearColor& Color)
{ DrawText(Text,Color,X,Y,GEngine ? GEngine->GetMediumFont():nullptr,Scale*1.35f,false); }
void ATrainingHUD::Panel(float X,float Y,float Width,float Height,float Alpha)
{
    DrawRect(FLinearColor(.013f,.022f,.036f,Alpha),X,Y,Width,Height);
    DrawRect(FLinearColor(.15f,.75f,.69f,.85f),X,Y,3.0f,Height);
}
void ATrainingHUD::DrawHUD()
{
    Super::DrawHUD(); if(!Canvas) return;
    if(!Scene.IsValid()) for(TActorIterator<ATrainingScene> It(GetWorld());It;++It) { Scene=*It; break; }
    if(!Scene.IsValid()) return;
    const ATrainingScene* S=Scene.Get(); const float W=Canvas->ClipX,H=Canvas->ClipY;
    const float U=FMath::Clamp(W/1440.0f,.7f,1.6f), M=25*U;
    const FLinearColor White(.91f,.95f,.97f,1),Muted(.56f,.67f,.72f,1),Teal(.22f,.94f,.79f,1),Amber(1,.68f,.25f,1);
    const bool Connected=S->IsPhysicsConnected(),Detail=S->GetViewName()==TEXT("JAW DETAIL");
    const bool Stopped=Connected && !S->IsPhysicsHealthy();
    const bool Protected=S->HasProtectionNotice() || Stopped;
    auto T=[&](const FString& Text,float X,float Y,float Size,const FLinearColor& C) { Label(Text,X,Y,Size*U,C); };
    Panel(M,M,446*U,134*U);
    T(TEXT("ENDO / FORGE"),M+18*U,M+11*U,1.43f,White);
    T(TEXT("03   HOLD  /  TENSION  /  CUT"),M+19*U,M+48*U,.86f,Teal);
    T(FString::Printf(TEXT("ACTIVE: %s    [ C ] SWITCH"),*S->GetToolName()),M+19*U,M+76*U,.76f,White);
    T(S->IsGrasperLatched() ? (S->IsGrasperHolding() ? TEXT("GRASPER LATCHED / TISSUE HELD") : TEXT("GRASPER LATCHED / NO TISSUE")) :
        (S->GetActiveTool()==0 ? TEXT("F: LATCH GRASPER    SPACE: CLOSE ACTIVE TOOL") : TEXT("C: SELECT GRASPER    SPACE: CLOSE SCISSORS")),M+19*U,M+105*U,.65f,S->IsGrasperLatched()?Amber:Muted);
    const float SW=300*U,SX=W-M-SW;
    Panel(SX,M,SW,Detail ? 255*U:372*U);
    T(!Connected?TEXT("PHYSICS WAITING"):Stopped?TEXT("PHYSICS STOPPED"):Protected?TEXT("PROTECTION RELEASE"):TEXT("PHYSICS LIVE"),
        SX+16*U,M+13*U,.96f,Connected && !Protected?Teal:Amber);
    FString State=S->IsMotionLimited()?TEXT("RCM TRAVEL LIMIT"):S->GetActiveTool()==1 ?
        (S->IsJawClosed()?TEXT("SCISSOR CLOSURE"):TEXT("BLADES OPEN")):
        S->IsGraspActive()?TEXT("TISSUE HELD"):S->IsJawClosed()?TEXT("CLOSE / NO GRIP"):TEXT("JAWS OPEN");
    if(Protected) State=Stopped ? TEXT("PRESS R TO RESET") : TEXT("REPOSITION / REGRIP / R RESET");
    T(State,SX+16*U,M+43*U,.78f,Protected || S->IsMotionLimited()?Amber:Teal);
    auto Row=[&](const TCHAR* Name,const FString& Value,float Y)
    { T(Name,SX+16*U,M+Y*U,.70f,Muted); T(Value,SX+183*U,M+Y*U,.76f,White); };
    if(Detail)
    {
        Row(TEXT("Instrument"),S->GetToolName(),81);
        Row(TEXT("Blade length"),TEXT("14.5 mm"),108);
        Row(TEXT("Actual half-angle"),FString::Printf(TEXT("%.1f deg"),S->GetJawAngleDeg()),135);
        Row(TEXT("Roll"),FString::Printf(TEXT("%.1f deg"),S->GetRollDeg()),162);
        T(TEXT("C: inspect the other instrument"),SX+16*U,M+200*U,.69f,Teal);
        T(TEXT("TAB: return to endoscope"),SX+16*U,M+225*U,.69f,Muted);
    }
    else
    {
        Row(TEXT("Cut strokes"),FString::FromInt(S->GetCutCount()),81);
        Row(TEXT("Cut length"),FString::Printf(TEXT("%.1f mm"),S->GetCutLengthCm()*10),108);
        Row(TEXT("Connected pieces"),FString::FromInt(S->GetComponentCount()),135);
        Row(TEXT("Active contact load"),FString::Printf(TEXT("%.3f N"),S->GetContactForceNewton()),162);
        Row(TEXT("Insertion / swing"),FString::Printf(TEXT("%.0f / %.0f"),S->GetInsertionCm()*10,S->GetSwingAngleDeg()),189);
        Row(TEXT("SOFA solve"),FString::Printf(TEXT("%.2f ms"),S->GetSolveTimeMs()),216);
        Row(TEXT("Render"),FString::Printf(TEXT("%.0f fps"),S->GetFrameRate()),243);
        T(FString::Printf(TEXT("%d FEM nodes  /  %d render vertices"),S->GetPhysicsNodeCount(),S->GetVertexCount()),SX+16*U,M+278*U,.65f,Muted);
        T(Protected?S->GetPhysicsStatus().Left(43):TEXT("Thin membrane / physical edge separation"),SX+16*U,M+304*U,.62f,Protected?Amber:Muted);
        T(TEXT("Engineering model. Not clinically calibrated."),SX+16*U,M+329*U,.58f,Muted);
        T(TEXT("Insertion: mm  |  Swing: degrees"),SX+16*U,M+351*U,.62f,Muted);
    }
    if(!Detail && Connected && PlayerOwner)
    {
        FVector2D P;
        if(PlayerOwner->ProjectWorldLocationToScreen(S->GetToolTip(),P))
        {
            const FLinearColor Mark=S->GetActiveTool()==1?Amber:Teal;
            const float R=11*U;
            DrawLine(P.X-R,P.Y,P.X-4*U,P.Y,Mark,1);
            DrawLine(P.X+4*U,P.Y,P.X+R,P.Y,Mark,1);
            DrawLine(P.X,P.Y-R,P.X,P.Y-4*U,Mark,1);
            DrawLine(P.X,P.Y+4*U,P.X,P.Y+R,Mark,1);
            T(S->GetToolName(),P.X+17*U,P.Y-10*U,.65f,Mark);
            FVector2D Command;
            if(FVector::Distance(S->GetCommandedTip(),S->GetToolTip())>.12 && PlayerOwner->ProjectWorldLocationToScreen(S->GetCommandedTip(),Command))
            {
                DrawLine(Command.X-4*U,Command.Y-4*U,Command.X+4*U,Command.Y+4*U,White,1);
                DrawLine(Command.X-4*U,Command.Y+4*U,Command.X+4*U,Command.Y-4*U,White,1);
            }
        }
        if(PlayerOwner->ProjectWorldLocationToScreen(S->GetOtherToolTip(),P))
            T(S->GetActiveTool()==1?(S->IsGrasperHolding()?TEXT("GRASPER / HOLD"):TEXT("GRASPER")):TEXT("SCISSORS"),
                P.X+12*U,P.Y+12*U,.57f,Muted);
    }
    const bool Help=S->IsHelpVisible()&&!Detail;
    const float BH=Help?184.0f:63.0f,BY=H-M-BH*U;
    Panel(M,BY,905*U,BH*U,.86f);
    T(Detail?TEXT("INSTRUMENT DETAIL"):TEXT("BIMANUAL MEMBRANE EXERCISE"),M+18*U,BY+10*U,.83f,Teal);
    T(Detail?TEXT("C: switch instrument   TAB: next view   H: help"):S->GetActionHint(),M+18*U,BY+35*U,.64f,White);
    if(Help)
    {
        T(TEXT("RMB + mouse / arrows: XY   W / S: height   T / G: insert / retract   CTRL: fine   Q / E: roll"),M+18*U,BY+71*U,.69f,White);
        T(TEXT("F: latch selected grasper / release held tissue   C: switch   Hold SPACE: close   Release: open"),M+18*U,BY+98*U,.69f,White);
        T(TEXT("1 / R: reset   2: ready to grasp (resets)   3: scissors approach (keeps tissue)   TAB: views"),M+18*U,BY+125*U,.69f,Muted);
        T(TEXT("Reopen scissors before each new bite.   ESC: release both + mouse   H: hide help   F10: exit"),M+18*U,BY+152*U,.68f,Muted);
    }
    if(!Connected && !S->IsVisualPreview())
    {
        const float PX=(W-590*U)*.5f;
        Panel(PX,H*.44f,590*U,88*U,.94f);
        T(TEXT("Waiting for the SOFA physics service"),PX+20*U,H*.44f+15*U,1.02f,Amber);
        T(TEXT("Tools release when the connection becomes unavailable."),PX+20*U,H*.44f+51*U,.73f,White);
    }
    T(FString::Printf(TEXT("%s / SESSION %05d"),*S->GetViewName(),S->GetResetCount()+1),
        W-M-280*U,H-M-20*U,.64f,Muted);
}
