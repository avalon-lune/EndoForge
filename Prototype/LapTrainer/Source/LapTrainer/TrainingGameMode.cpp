#include "TrainingGameMode.h"
#include "TrainingScene.h"
#include "TrainingHUD.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"

ATrainingGameMode::ATrainingGameMode()
{
    DefaultPawnClass = nullptr;
    HUDClass = ATrainingHUD::StaticClass();
    PlayerControllerClass = APlayerController::StaticClass();
}

void ATrainingGameMode::BeginPlay()
{
    Super::BeginPlay();
    GetWorld()->SpawnActor<ATrainingScene>();
}
