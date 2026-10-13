#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "TrainingGameMode.generated.h"

UCLASS()
class LAPTRAINER_API ATrainingGameMode : public AGameModeBase
{
    GENERATED_BODY()
public:
    ATrainingGameMode();
protected:
    virtual void BeginPlay() override;
};
