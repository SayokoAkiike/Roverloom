#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"

#include "RaceOpponent.generated.h"

class AWheelRig;
class UPhysicalMaterial;
class UStaticMeshComponent;

// An NPC rival or a ghost in the race: a look-alike of the rover in its paint.
// A ghost is a record of an earlier run: drawn where Python puts it, eased toward each pose, with no collision.
// An NPC is physical (EnablePhysics): the same six-wheel rig as the player's rover, driven by Python's command (speed
// and turn rate), so it collides with the player, with other rivals and with solid props and rocks, and pushes back.
// Unreal's physics decides where it is; the pawn reports that pose to Python in its telemetry.
UCLASS(NotBlueprintable)
class ARaceOpponent : public AActor
{
	GENERATED_BODY()

public:
	ARaceOpponent();

	virtual void Tick(float DeltaSeconds) override;
	virtual void Destroyed() override;

	// Site frame: metres and radians, positive yaw turning left. bGhost draws it pale and half sunk in dust colour.
	void SetTarget(const FVector2D& SiteM, double SiteYawRad, const FLinearColor& Paint, bool bGhost);

	// Physics: spawn a rig on the ground at the current target pose. Python then drives it with SetCommand.
	void EnablePhysics();
	bool IsPhysical() const { return Rig != nullptr; }
	void SetCommand(double LinearMps, double YawRateRadps);
	// Put the rig back on the ground at a pose (site frame), at rest: Python's rescue of a stuck rival.
	void ResetTo(const FVector2D& SiteM, double SiteYawRad);
	// The rig's pose and forward speed in the site frame; false until the rig simulates.
	bool GetSitePose(FVector2D& OutM, double& OutYawRad, double& OutForwardMps) const;

	FString DisplayName;
	int32 Position = 0;
	bool bIsGhost = false;
	double LastUpdateS = -1.0;
	int32 LastResetId = 0;

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

	double GroundBelowCm(const FVector& AtCm) const;
	void TickPhysical(double DeltaSeconds);
	UPROPERTY()
	TObjectPtr<AWheelRig> Rig;
	UPROPERTY()
	TObjectPtr<UPhysicalMaterial> RigMaterial;
	bool bRigReady = false;
	double CommandMps = 0.0;
	double CommandRadps = 0.0;
	FTransform ResetPose;
};
