#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"

#include "SpikeParameters.h"

#include "SpikeRover.generated.h"

class UPhysicalMaterial;
class UPhysicsConstraintComponent;
class UStaticMeshComponent;

// R0 rover for the physics spike: a box body and six sphere wheels on driven hinges, no suspension.
UCLASS(NotBlueprintable)
class ASpikeRover : public AActor
{
	GENERATED_BODY()

public:
	ASpikeRover();

	// Creates bodies at the actor's transform. A pinned chassis does not simulate.
	// The torque limit is RoverloomSpike::DriveMaxTorque unless a diagnostic run overrides it. 0 means no limit.
	void Build(UPhysicalMaterial* Material, bool bPinChassis, double InDriveMaxTorque);

	// Starts simulation and creates the joints once the bodies exist. Returns false until then.
	// After it returns true, IsConnected says whether every joint was created.
	bool TryConnect();
	bool IsConnected() const { return bConnected; }

	// Unreal yaw rate: positive turns right, seen from above. Clamped to the design limits.
	void SetCommand(double ForwardCmps, double YawRateDegps);

	UStaticMeshComponent* GetChassis() const { return Chassis; }
	FVector GetWheelLocation(int32 Index) const;

	// Wheel spin relative to the chassis about the chassis's right axis, rad/s. Positive rolls forward.
	double GetWheelSpinRadps(int32 Index) const;
	double GetWheelTargetRadps(int32 Index) const { return TargetSpinRadps[Index]; }

	// Force on the chassis through each axle, summed, in kg cm / s^2. Zero if Chaos reports none.
	FVector GetAxleForceSum() const;

	// Collision shapes found on the engine meshes, for the run record.
	FString DescribeCollision() const;

private:
	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> Chassis;

	UPROPERTY()
	TArray<TObjectPtr<UStaticMeshComponent>> Wheels;

	UPROPERTY()
	TArray<TObjectPtr<UPhysicsConstraintComponent>> Axles;

	double TargetSpinRadps[RoverloomSpike::NumWheels] = {};
	bool bPinned = false;
	double DriveTorqueLimit = RoverloomSpike::DriveMaxTorque;
	bool bConnected = false;
};
