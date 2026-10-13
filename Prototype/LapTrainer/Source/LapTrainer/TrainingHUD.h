#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "TrainingHUD.generated.h"

class ATrainingScene;

UCLASS()
class LAPTRAINER_API ATrainingHUD : public AHUD
{
    GENERATED_BODY()

public:
    virtual void DrawHUD() override;

private:
    TWeakObjectPtr<ATrainingScene> Scene;
    void Label(const FString& Text, float X, float Y, float Scale, const FLinearColor& Color);
    void Panel(float X, float Y, float Width, float Height, float Alpha = 0.84f);
};
