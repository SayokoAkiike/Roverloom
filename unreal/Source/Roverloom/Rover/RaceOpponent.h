#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"

#include "RaceOpponent.generated.h"

class UStaticMeshComponent;

// An NPC rival or a ghost in the race, drawn where Python's race model puts it. It has no collision and no physics:
// a look-alike of the rover in its paint, eased toward each new pose and set on the ground below it.
UCLASS(NotBlueprintable)
class ARaceOpponent : public AActor
{
	GENERATED_BODY()

public:
	ARaceOpponent();

	virtual void Tick(float DeltaSeconds) override;

	// Site frame: metres and radians, positive yaw turning left. bGhost draws it pale and half sunk in dust colour.
	void SetTarget(const FVector2D& SiteM, double SiteYawRad, const FLinearColor& Paint, bool bGhost);

	FString DisplayName;
	int32 Position = 0;
	bool bIsGhost = false;
	double LastUpdateS = -1.0;

private:
	UPROPERTY()
	TObjectPtr<USceneComponent> Root;
	UPROPERTY()
	TArray<TObjectPtr<UStaticMeshComponent>> Meshes;
	TArray<double> WheelSpin;

	FVector TargetCm = FVector::ZeroVector;
	double TargetYawDeg = 0.0;
	bool bHasTarget = false;
	bool bPainted = false;
	FLinearColor LastPaint = FLinearColor::Black;
	double GroundCm = 0.0;
	int32 TraceFrame = 0;
};
