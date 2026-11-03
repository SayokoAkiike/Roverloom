#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"

#include "WheelModel.h"

#include "WheelRig.generated.h"

class UPhysicalMaterial;
class UStaticMeshComponent;

// One rigid body carried by model wheels. Wheels are not bodies: each traces to the ground and applies a force.
UCLASS(NotBlueprintable)
class AWheelRig : public AActor
{
	GENERATED_BODY()

public:
	AWheelRig();

	struct FWheelSetup
	{
		FVector MountLocal = FVector::ZeroVector; // On the body, relative to its center, in cm.
		bool bLeft = false;
	};

	struct FWheelRecord
	{
		RoverloomWheel::FWheelContact Contact;
		RoverloomWheel::FWheelResult Result;
		double SpinRadps = 0.0;
		double TargetSpinRadps = 0.0;
	};

	// Box size in cm, mass, wheels, and which rotation axes are locked. Bodies exist only after registration.
	void Build(const FVector& SizeCm, double MassKg, const TArray<FWheelSetup>& InWheels, bool bLockRollPitch, bool bLockYaw,
		bool bSweep, double Friction, UPhysicalMaterial* BodyMaterial);
	bool IsReady() const;

	// Per-wheel target spin, and a mode for all wheels.
	void SetTargets(const TArray<double>& TargetSpinRadps, RoverloomWheel::EWheelMode Mode);

	// One physics step: trace, solve every wheel, and apply forces for the coming step.
	void StepWheels(double Dt);

	UStaticMeshComponent* GetBody() const { return Body; }
	const TArray<FWheelRecord>& GetRecords() const { return Records; }
	const RoverloomWheel::FWheelParams& GetParams() const { return Params; }
	int32 NumWheels() const { return Wheels.Num(); }

private:
	double InverseMassAlong(const FVector& Point, const FVector& Direction) const;

	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> Body;

	TArray<FWheelSetup> Wheels;
	TArray<FWheelRecord> Records;
	TArray<double> Spins;
	TArray<double> Targets;
	RoverloomWheel::EWheelMode Mode = RoverloomWheel::EWheelMode::Drive;
	RoverloomWheel::FWheelParams Params;
	double MassKg = 1.0;
	bool bLockRollPitchAxes = false;
	bool bLockYawAxis = false;
	bool bUseSweep = false;
};
