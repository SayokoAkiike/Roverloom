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
		bool bStartPenetrating = false; // The trace started inside geometry; compression is the full travel.
	};

	// Box size in cm, mass, wheels, and which rotation axes are locked. Bodies exist only after registration.
	void Build(const FVector& SizeCm, double MassKg, const TArray<FWheelSetup>& InWheels, bool bLockRollPitch, bool bLockYaw,
		bool bSweep, double Friction, UPhysicalMaterial* BodyMaterial);
	bool IsReady() const;

	// Per-wheel target spin, and a mode for all wheels.
	void SetTargets(const TArray<double>& TargetSpinRadps, RoverloomWheel::EWheelMode Mode);

	// Solver diagnostics, off by default. A warm start begins each wheel from its last force, projected onto the
	// current contact plane, and only if the wheel touched the ground on both steps. A shadow solve repeats each step
	// with many more passes, for comparison only; its forces are never applied.
	struct FDiagnostics
	{
		RoverloomWheel::FSolverOptions Options;
		bool bWarmStart = false;
		bool bShadow = false;
		FString DumpPath; // If set, the next step's solver input and result are written there as one JSON line, once.
		bool bDumpAppend = false;
	};
	struct FShadowRecord
	{
		double ForceDifference = 0.0;     // Largest single-wheel tangential force difference over mu Fz
		double NetForceDifference = 0.0;  // |difference of the tangential net force|
		double NetTorqueDifference = 0.0; // |difference of its torque about the center of mass|
		double NaturalResidual = 0.0;
		int32 Passes = 0;
	};
	void SetDiagnostics(const FDiagnostics& InDiagnostics) { Diagnostics = InDiagnostics; }
	void RequestDump(const FString& Path, bool bAppend = false)
	{
		Diagnostics.DumpPath = Path;
		Diagnostics.bDumpAppend = bAppend;
	}
	const FShadowRecord& GetShadow() const { return Shadow; }
	double GetSolveMicros() const { return SolveMicros; }

	// A known force on the center of mass for the coming step. The rig applies it, and the solve accounts for it.
	void SetExternalForce(const FVector& Force) { ExternalForce = Force; }

	// One physics step: trace, solve all wheels together, and apply forces for the coming step.
	void StepWheels(double Dt);

	UStaticMeshComponent* GetBody() const { return Body; }
	const TArray<FWheelRecord>& GetRecords() const { return Records; }
	const RoverloomWheel::FSolveStats& GetSolveStats() const { return Stats; }
	// Sum of the wheels' forces on the body, and their torque about its center of mass, for the coming step.
	const FVector& GetWheelForce() const { return WheelForce; }
	const FVector& GetWheelTorque() const { return WheelTorque; }
	// Rigid-body hits on the box itself, which the wheel solve does not know about.
	int32 GetBodyHits() const { return BodyHits; }
	// The inverse inertia rows the solve used on the last step.
	const RoverloomWheel::FBodyState& GetLastBodyState() const { return LastBodyState; }
	const RoverloomWheel::FWheelParams& GetParams() const { return Params; }
	int32 NumWheels() const { return Wheels.Num(); }

private:
	// The body as Chaos will integrate it this step, with locked rotation axes removed from its inverse inertia.
	RoverloomWheel::FBodyState BodyState() const;
	void DumpSolverStep(const FString& Path, bool bAppend, TConstArrayView<RoverloomWheel::FWheelContact> Contacts,
		TConstArrayView<RoverloomWheel::FWheelCommand> Commands, double Dt, TConstArrayView<double> SpinsBefore,
		TConstArrayView<RoverloomWheel::FWheelResult> Results) const;

	UFUNCTION()
	void OnBodyHit(UPrimitiveComponent* HitComponent, AActor* OtherActor, UPrimitiveComponent* OtherComp, FVector NormalImpulse,
		const FHitResult& Hit);

	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> Body;

	TArray<FWheelSetup> Wheels;
	TArray<FWheelRecord> Records;
	TArray<double> Spins;
	TArray<double> Targets;
	RoverloomWheel::EWheelMode Mode = RoverloomWheel::EWheelMode::Drive;
	RoverloomWheel::FWheelParams Params;
	RoverloomWheel::FSolveStats Stats;
	FVector ExternalForce = FVector::ZeroVector;
	FVector WheelForce = FVector::ZeroVector;
	FVector WheelTorque = FVector::ZeroVector;
	RoverloomWheel::FBodyState LastBodyState;
	int32 BodyHits = 0;
	FDiagnostics Diagnostics;
	FShadowRecord Shadow;
	double SolveMicros = 0.0;
	TArray<FVector> LastTraction; // World tangential force per wheel from the last step; zero if it had no contact
	double MassKg = 1.0;
	bool bLockRollPitchAxes = false;
	bool bLockYawAxis = false;
	bool bUseSweep = false;
};
