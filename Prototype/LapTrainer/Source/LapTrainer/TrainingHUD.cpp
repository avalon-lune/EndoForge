#include "TrainingHUD.h"
#include "TrainingScene.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"

void ATrainingHUD::Label(const FString& Text, float X, float Y, float Scale, const FLinearColor& Color)
{
    DrawText(Text, Color, X, Y, GEngine ? GEngine->GetMediumFont() : nullptr, Scale * 1.35f, false);
}

void ATrainingHUD::Panel(float X, float Y, float Width, float Height, float Alpha)
{
    DrawRect(FLinearColor(0.013f, 0.022f, 0.036f, Alpha), X, Y, Width, Height);
    DrawRect(FLinearColor(0.15f, 0.75f, 0.69f, 0.85f), X, Y, 3.0f, Height);
}

void ATrainingHUD::DrawHUD()
{
    Super::DrawHUD();
    if (!Canvas) return;
    if (!Scene.IsValid())
        for (TActorIterator<ATrainingScene> It(GetWorld()); It; ++It) { Scene = *It; break; }
    if (!Scene.IsValid()) return;
    const ATrainingScene* S = Scene.Get();
    const float W = Canvas->ClipX, H = Canvas->ClipY;
    const float U = FMath::Clamp(W / 1440.0f, 0.7f, 1.6f), Margin = 25.0f * U;
    const FLinearColor White(0.91f, 0.95f, 0.97f, 1.0f), Muted(0.56f, 0.67f, 0.72f, 1.0f);
    const FLinearColor Teal(0.22f, 0.94f, 0.79f, 1.0f), Amber(1.0f, 0.68f, 0.25f, 1.0f);
    const bool Connected = S->IsPhysicsConnected(), Preview = S->IsVisualPreview();
    const bool Detail = S->GetViewName() == TEXT("JAW DETAIL");
    auto T = [&](const FString& Text, float X, float Y, float Size, const FLinearColor& Color)
    { Label(Text, X, Y, Size * U, Color); };

    Panel(Margin, Margin, 460.0f * U, 105.0f * U);
    T(TEXT("LAP / TRAINER"), Margin + 18 * U, Margin + 12 * U, 1.43f, White);
    T(TEXT("02   CONTACT  /  FRICTION  /  TISSUE"), Margin + 19 * U, Margin + 47 * U, 0.82f, Teal);
    T(Preview ? TEXT("GEOMETRY PREVIEW - physics is not being verified") : TEXT("UE5 + SOFA  |  Engineering prototype"),
        Margin + 19 * U, Margin + 77 * U, 0.68f, Preview ? Amber : Muted);

    const float SW = 306.0f * U, SX = W - Margin - SW;
    Panel(SX, Margin, SW, (Detail ? 267.0f : 348.0f) * U);
    T(Preview ? TEXT("VISUAL INSPECTION") : Connected ? TEXT("PHYSICS  LIVE") : TEXT("PHYSICS  WAITING"),
        SX + 16 * U, Margin + 13 * U, 0.98f, Connected ? Teal : Amber);
    FString State = S->IsMotionLimited() ? TEXT("RCM TRAVEL LIMIT") : S->IsSlipping() ? TEXT("FRICTIONAL SLIDING") :
        S->IsGraspActive() ? TEXT("BILATERAL GRASP") : S->GetContactCount() > 0 ? TEXT("JAW CONTACT") :
        S->IsJawClosed() ? TEXT("CLOSE COMMAND / NO GRIP") : TEXT("JAWS OPEN");
    T(State, SX + 16 * U, Margin + 43 * U, 0.77f, S->IsSlipping() || S->IsMotionLimited() ? Amber : Teal);
    auto Row = [&](const TCHAR* Name, const FString& Value, float Y, const FLinearColor& Color)
    {
        T(Name, SX + 16 * U, Margin + Y * U, 0.74f, Muted);
        T(Value, SX + 190 * U, Margin + Y * U, 0.78f, Color);
    };
    if (Detail)
    {
        Row(TEXT("Jaw length"), TEXT("14.5 mm"), 81, White);
        Row(TEXT("Jaw width / thickness"), TEXT("2.5 / 1.4"), 108, White);
        Row(TEXT("Actual half-angle"), FString::Printf(TEXT("%.1f deg"), S->GetJawAngleDeg()), 135, White);
        Row(TEXT("Roll"), FString::Printf(TEXT("%.1f deg"), S->GetRollDeg()), 162, White);
        T(TEXT("Bevels, teeth and shallow grooves"), SX + 16 * U, Margin + 198 * U, 0.70f, Muted);
        T(TEXT("remain within the collision envelope."), SX + 16 * U, Margin + 220 * U, 0.66f, Muted);
        T(TEXT("TAB returns to the endoscope view"), SX + 16 * U, Margin + 244 * U, 0.65f, Teal);
    }
    else
    {
        Row(TEXT("Contact constraints"), FString::FromInt(S->GetContactCount()), 81, White);
        Row(TEXT("Contact load"), FString::Printf(TEXT("%.2f N"), S->GetContactForceNewton()), 108, White);
        Row(TEXT("Residual penetration"), FString::Printf(TEXT("%.3f mm"), S->GetPenetrationMm()), 135, White);
        Row(TEXT("Sliding distance"), FString::Printf(TEXT("%.2f mm"), S->GetSlipDistanceMm()), 162, S->IsSlipping() ? Amber : White);
        Row(TEXT("Insertion / swing"), FString::Printf(TEXT("%.0f / %.0f"), S->GetInsertionCm() * 10, S->GetSwingAngleDeg()), 189, White);
        Row(TEXT("SOFA solve"), FString::Printf(TEXT("%.2f ms"), S->GetSolveTimeMs()), 216, White);
        Row(TEXT("Render"), FString::Printf(TEXT("%.0f fps"), S->GetFrameRate()), 243, White);
        T(Connected ? FString::Printf(TEXT("%d FEM nodes  /  %d render vertices"), S->GetPhysicsNodeCount(), S->GetVertexCount()) :
            TEXT("FEM nodes: N/A  /  static visual preview"),
            SX + 16 * U, Margin + 279 * U, 0.67f, Muted);
        T(TEXT("Material and forces are not clinically calibrated."), SX + 16 * U, Margin + 307 * U, 0.58f, Muted);
        T(TEXT("Insertion: mm   |   Swing: degrees"), SX + 16 * U, Margin + 328 * U, 0.61f, Muted);
    }

    if (!Detail && !Preview)
    {
        FVector2D P;
        if (PlayerOwner && PlayerOwner->ProjectWorldLocationToScreen(S->GetToolTip(), P))
        {
            const FLinearColor Mark = S->IsSlipping() ? Amber : S->IsGraspActive() || S->GetContactCount() > 0 ? Teal : White;
            const float R = 11 * U;
            DrawLine(P.X - R, P.Y, P.X - 4 * U, P.Y, Mark, 1);
            DrawLine(P.X + 4 * U, P.Y, P.X + R, P.Y, Mark, 1);
            DrawLine(P.X, P.Y - R, P.X, P.Y - 4 * U, Mark, 1);
            DrawLine(P.X, P.Y + 4 * U, P.X, P.Y + R, Mark, 1);
            T(S->IsSlipping() ? TEXT("SLIDING") : S->IsGraspActive() ? TEXT("GRIP") :
                S->GetContactCount() > 0 ? TEXT("CONTACT") : TEXT("ACTUAL TIP"),
                P.X + 17 * U, P.Y - 10 * U, 0.66f, Mark);
            FVector2D Command;
            if (FVector::Distance(S->GetCommandedTip(), S->GetToolTip()) > 0.12 &&
                PlayerOwner->ProjectWorldLocationToScreen(S->GetCommandedTip(), Command))
            {
                DrawLine(Command.X - 4 * U, Command.Y - 4 * U, Command.X + 4 * U, Command.Y + 4 * U, Amber, 1);
                DrawLine(Command.X - 4 * U, Command.Y + 4 * U, Command.X + 4 * U, Command.Y - 4 * U, Amber, 1);
                DrawLine(P.X, P.Y, Command.X, Command.Y, FLinearColor(1, .68f, .25f, .3f), 1);
            }
        }
    }

    const bool Help = S->IsHelpVisible() && !Detail;
    const float BH = Help ? 156.0f : 58.0f, BY = H - Margin - BH * U;
    Panel(Margin, BY, 870 * U, BH * U, 0.86f);
    T(Detail ? TEXT("JAW DETAIL / NATIVE PROCEDURAL GEOMETRY") :
        S->GetPreset() == 2 ? TEXT("PRESET 2 / EDGE GRASP") : TEXT("PRESET 1 / SURFACE CONTACT"),
        Margin + 18 * U, BY + 10 * U, 0.83f, Teal);
    T(Preview ? TEXT("Static geometry preview. This image is not a physics acceptance test.") :
        Detail ? TEXT("TAB: next view   H: help   Geometry follows the authoritative SOFA jaw poses.") : S->GetActionHint(),
        Margin + 18 * U, BY + 33 * U, 0.69f, White);
    if (Help)
    {
        T(TEXT("RMB + mouse / arrows: XY   W / S: height   T / G: insert / retract   CTRL: fine motion"),
            Margin + 18 * U, BY + 69 * U, 0.73f, White);
        T(TEXT("Hold SPACE: close   Release SPACE: open   Q / E: roll   1: surface preset   2: edge preset"),
            Margin + 18 * U, BY + 95 * U, 0.73f, White);
        T(TEXT("R: reset   TAB: four views   H: help   ESC: release mouse   F10: exit"),
            Margin + 18 * U, BY + 122 * U, 0.73f, Muted);
    }
    if (!Connected && !Preview)
    {
        const float PX = (W - 590 * U) * 0.5f;
        Panel(PX, H * 0.44f, 590 * U, 88 * U, 0.94f);
        T(TEXT("Waiting for the SOFA physics service"), PX + 20 * U, H * 0.44f + 15 * U, 1.02f, Amber);
        T(TEXT("The tissue remains static until a valid physical state arrives."),
            PX + 20 * U, H * 0.44f + 51 * U, 0.73f, White);
    }
    T(FString::Printf(TEXT("%s  /  SESSION %05d"), *S->GetViewName(), S->GetResetCount() + 1),
        W - Margin - 274 * U, H - Margin - 20 * U, 0.66f, Muted);
}
