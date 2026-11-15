#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"

#include "WheelModel.h"

#include "WheelSpikeGameMode.generated.h"

class AWheelRig;
class UPhysicalMaterial;

// Runs one wheel model scenario, writes its record to -SpikeOut, and exits. Start it with
// /Engine/Maps/Entry?game=/Script/Roverloom.WheelSpikeGameMode -game -WheelScenario=<id>.
UCLASS(NotBlueprintable)
class AWheelSpikeGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AWheelSpikeGameMode();

	virtual void StartPlay() override;
	virtual void Tick(float DeltaSeconds) override;

private:
	void SpawnBlock(const FVector& Center, const FRotator& Rotation, const FVector& SizeCm);
	void Command(double TimeS, TArray<double>& OutTargets, RoverloomWheel::EWheelMode& OutMode, FVector& OutPush);
	void CommandSix(double TimeS, TArray<double>& OutTargets, RoverloomWheel::EWheelMode& OutMode, FVector& OutPush);
	void Record(double DeltaSeconds, double WallFrameMs, const FVector& Push);
	void Finish(const FString& Outcome);

	UPROPERTY()
	TObjectPtr<AWheelRig> Rig;

	UPROPERTY()
	TObjectPtr<UPhysicalMaterial> Material;

	FString Scenario;
	FString OutDir;
	bool bPair = false;
	bool bSix = false;
	bool bSleepAllowed = true;
	double DumpAtS = -1.0;
	int32 DumpEvery = 0;
	double DumpFromS = 0.0;
	double DumpToS = 1.0e9;
	FString SolverLabel;
	double StepCm = 0.0;
	FRandomStream Random;
	double NextRandomChangeS = 0.0;
	double RandomForwardCmps = 0.0;
	double RandomYawRateDegps = 0.0;
	double LastWallS = 0.0;
	bool bSweep = false;
	double Friction = 0.6;
	double SlopeDeg = 0.0;
	double DurationS = 0.0;
	double SimTimeS = 0.0;
	int64 Frame = 0;
	bool bStarted = false;
	bool bFinished = false;
	TArray<FString> Rows;
};
