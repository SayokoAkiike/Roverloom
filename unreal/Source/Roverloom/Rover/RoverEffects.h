#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"

#include "RoverEffects.generated.h"

class ARoverPawn;
class UDecalComponent;
class UInstancedStaticMeshComponent;
class UMaterialInterface;

// Looks only: wheel ruts as decals, and dust as soft particles. It reads the rover's pose and speed and never writes to it, and
// nothing here has collision, so no physics value depends on it.
//
// Why not Niagara: the Niagara template systems in UE 5.8.4 expose no parameters (probed 2026-11-16 with -RoverNiagaraProbe: all six
// templates list 0 exposed variables), and Editor Python cannot edit emitters, so a template cannot be restyled as dust from code.
// The particles are simulated here instead, on the CPU, as instances of a sphere with a soft translucent material, at Mars's
// gravity (3.71 m/s^2, about 38% of Earth's), with a little drag and a wind.
//
// Three kinds of dust: puffs thrown up by each rolling wheel, a thin haze that drifts with the wind around the rover, and a dust
// devil in the distance. Ruts: a decal for every 14 cm each wheel rolls, in a ring of fixed size, so the oldest are overwritten.
UCLASS(NotBlueprintable)
class ARoverEffects : public AActor
{
	GENERATED_BODY()

public:
	ARoverEffects();

	// Returns false when the effect materials are missing (they live outside Git), and then nothing is drawn.
	bool Init(ARoverPawn* InRover, bool bInDust, bool bInRuts);

	virtual void Tick(float DeltaSeconds) override;

private:
	enum class EKind : uint8
	{
		Wheel,
		Haze,
		Devil
	};
	struct FPuff
	{
		EKind Kind = EKind::Wheel;
		bool bAlive = false;
		FVector Position = FVector::ZeroVector;
		FVector Velocity = FVector::ZeroVector;
		double Age = 0.0;
		double Life = 1.0;
		double Size0 = 10.0; // Diameter at birth and at death, cm
		double Size1 = 30.0;
		double Alpha = 0.3;
		double Angle = 0.0; // Dust devil: where around the column, and how fast it turns
		double Omega = 2.0;
		double Climb = 1000.0; // Dust devil: cm per second upward
		double Spread = 0.0;
	};

	void EmitWheelDust(const FVector& Ground, const FVector& Travel, double SpeedFraction);
	void SpawnHaze(FPuff& P, bool bAnyAge);
	void SpawnDevil(FPuff& P, bool bAnyAge);
	void Simulate(double Dt);
	void DropRuts(double Dt, const FTransform& Body, double SpeedMps);
	bool GroundAt(double X, double Y, FVector& OutPoint) const;

	UPROPERTY()
	TObjectPtr<ARoverPawn> Rover;
	UPROPERTY()
	TObjectPtr<UInstancedStaticMeshComponent> Puffs;
	UPROPERTY()
	TArray<TObjectPtr<UDecalComponent>> Decals;
	UPROPERTY()
	TObjectPtr<UMaterialInterface> RutMaterial;

	TArray<FPuff> Particles;
	int32 WheelFirst = 0, WheelCount = 0, HazeFirst = 0, HazeCount = 0, DevilFirst = 0, DevilCount = 0;
	int32 WheelCursor = 0;
	double Carry[6] = {};
	FVector LastRut[6];
	bool bHaveRut[6] = {};
	int32 NextDecal = 0;
	int32 DecalsMade = 0;
	FVector DevilCenter = FVector::ZeroVector;
	double DevilAge = 0.0;
	double DevilGroundTimer = 0.0;
	FRandomStream Random;
	bool bDust = true;
	bool bRuts = true;
	double LogTimer = 0.0;
};
