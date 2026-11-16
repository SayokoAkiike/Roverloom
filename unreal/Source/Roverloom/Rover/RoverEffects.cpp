#include "RoverEffects.h"

#include "Components/DecalComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SceneComponent.h"
#include "Engine/CollisionProfile.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Materials/MaterialInterface.h"
#include "UObject/ConstructorHelpers.h"

#include "../Roverloom.h"
#include "RoverDrive.h"
#include "RoverPawn.h"

namespace
{
	constexpr double MarsGravityCmps2 = 371.0; // 3.71 m/s^2, about 38% of Earth's
	constexpr int32 WheelPuffs = 700;
	constexpr int32 HazePuffs = 120;
	constexpr int32 DevilPuffs = 260;
	constexpr int32 MaxDecals = 1800;
	constexpr double RutSpacingCm = 14.0;
	constexpr double RutLengthCm = 26.0; // Longer than the spacing, so that neighbours overlap and blend
	constexpr double RutHalfWidthCm = 10.5; // The wheel is 20 cm wide
	const FVector WindCmps(-40.0, 28.0, 0.0); // About 0.5 m/s, toward -X and +Y; dust drifts downwind
	const FVector DevilOffsetCm(16000.0, 9000.0, 0.0); // Where the dust devil starts, 185 m from the rover
}

ARoverEffects::ARoverEffects()
{
	PrimaryActorTick.bCanEverTick = true;
	USceneComponent* Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(Root);

	Puffs = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("Puffs"));
	Puffs->SetupAttachment(Root);
	Puffs->SetMobility(EComponentMobility::Movable);
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Sphere(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	Puffs->SetStaticMesh(Sphere.Object);
	Puffs->NumCustomDataFloats = 1; // The opacity of each puff
	Puffs->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Puffs->SetCollisionProfileName(UCollisionProfile::NoCollision_ProfileName);
	Puffs->SetCastShadow(false);
	Puffs->bReceivesDecals = false;
	Puffs->bAffectDynamicIndirectLighting = false;
	Puffs->bAffectDistanceFieldLighting = false;
	Puffs->SetCanEverAffectNavigation(false);
	Random.Initialize(20261116);
}

bool ARoverEffects::Init(ARoverPawn* InRover, bool bInDust, bool bInRuts)
{
	Rover = InRover;
	bDust = bInDust;
	bRuts = bInRuts;
	UMaterialInterface* DustMaterial = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Licensed/Gale/M_DustParticle.M_DustParticle"), nullptr, LOAD_NoWarn | LOAD_Quiet);
	RutMaterial = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Licensed/Gale/M_RutDecal.M_RutDecal"), nullptr, LOAD_NoWarn | LOAD_Quiet);
	if (bDust && !DustMaterial)
	{
		UE_LOG(LogRoverloom, Display, TEXT("Rover effects: M_DustParticle not found (it lives outside Git); no dust"));
		bDust = false;
	}
	if (bRuts && !RutMaterial)
	{
		UE_LOG(LogRoverloom, Display, TEXT("Rover effects: M_RutDecal not found (it lives outside Git); no ruts"));
		bRuts = false;
	}
	if (!bDust && !bRuts)
	{
		return false;
	}
	if (bDust)
	{
		Puffs->SetMaterial(0, DustMaterial);
		const int32 Total = WheelPuffs + HazePuffs + DevilPuffs;
		Particles.SetNum(Total);
		WheelFirst = 0;
		WheelCount = WheelPuffs;
		HazeFirst = WheelPuffs;
		HazeCount = HazePuffs;
		DevilFirst = WheelPuffs + HazePuffs;
		DevilCount = DevilPuffs;
		const FTransform Hidden(FQuat::Identity, FVector(0.0, 0.0, -100000.0), FVector(0.001));
		for (int32 I = 0; I < Total; ++I)
		{
			Puffs->AddInstance(Hidden, true);
		}
		DevilCenter = Rover->GetActorLocation() + DevilOffsetCm;
		for (int32 I = 0; I < HazeCount; ++I)
		{
			SpawnHaze(Particles[HazeFirst + I], true);
		}
		for (int32 I = 0; I < DevilCount; ++I)
		{
			SpawnDevil(Particles[DevilFirst + I], true);
		}
	}
	else
	{
		Puffs->SetVisibility(false);
	}
	for (FVector& Point : LastRut)
	{
		Point = FVector::ZeroVector;
	}
	return true;
}

bool ARoverEffects::GroundAt(double X, double Y, FVector& OutPoint) const
{
	FHitResult Hit;
	const FVector Start(X, Y, Rover->GetActorLocation().Z + 300.0);
	const FVector End(X, Y, Rover->GetActorLocation().Z - 800.0);
	if (GetWorld()->LineTraceSingleByObjectType(Hit, Start, End, FCollisionObjectQueryParams(ECC_WorldStatic)))
	{
		OutPoint = Hit.ImpactPoint;
		return true;
	}
	return false;
}

void ARoverEffects::SpawnHaze(FPuff& P, bool bAnyAge)
{
	// A thin dust that drifts with the wind around the rover: large, faint, and slow, a few meters above the ground
	const FVector Center = Rover->GetActorLocation();
	P.Kind = EKind::Haze;
	P.bAlive = true;
	P.Life = Random.FRandRange(18.0, 40.0);
	P.Age = bAnyAge ? Random.FRandRange(0.0, P.Life) : 0.0;
	P.Position = Center + FVector(Random.FRandRange(-4000.0, 4000.0), Random.FRandRange(-4000.0, 4000.0), Random.FRandRange(-50.0, 250.0));
	P.Velocity = FVector(Random.FRandRange(-20.0, 20.0), Random.FRandRange(-20.0, 20.0), Random.FRandRange(-2.0, 6.0));
	P.Size0 = Random.FRandRange(120.0, 260.0);
	P.Size1 = Random.FRandRange(260.0, 520.0);
	P.Alpha = Random.FRandRange(0.07, 0.14);
}

void ARoverEffects::SpawnDevil(FPuff& P, bool bAnyAge)
{
	// A dust devil: puffs rise in a column that widens with height and turns, so the column reads as a spinning plume
	P.Kind = EKind::Devil;
	P.bAlive = true;
	P.Life = Random.FRandRange(6.0, 9.0);
	P.Age = bAnyAge ? Random.FRandRange(0.0, P.Life) : 0.0;
	P.Climb = Random.FRandRange(650.0, 1100.0);
	P.Angle = Random.FRandRange(0.0, 2.0 * PI);
	P.Omega = Random.FRandRange(1.4, 2.6);
	P.Spread = Random.FRandRange(-40.0, 60.0);
	P.Size0 = Random.FRandRange(180.0, 280.0);
	P.Size1 = Random.FRandRange(800.0, 1400.0);
	P.Alpha = Random.FRandRange(0.35, 0.6);
}

void ARoverEffects::EmitWheelDust(const FVector& Ground, const FVector& Travel, double SpeedFraction)
{
	// Rolling wheels kick dust up and back, a little: the rover is slow (0.5 m/s at most)
	for (int32 Tries = 0; Tries < WheelCount; ++Tries)
	{
		FPuff& P = Particles[WheelFirst + WheelCursor];
		WheelCursor = (WheelCursor + 1) % WheelCount;
		if (P.bAlive && Tries + 1 < WheelCount)
		{
			continue; // Take a free slot, or overwrite the one the cursor ends on
		}
		P.Kind = EKind::Wheel;
		P.bAlive = true;
		P.Age = 0.0;
		P.Life = Random.FRandRange(1.5, 4.8);
		P.Position = Ground + FVector(Random.FRandRange(-7.0, 7.0), Random.FRandRange(-7.0, 7.0), Random.FRandRange(2.0, 8.0));
		const FVector Back = -Travel * Random.FRandRange(8.0, 38.0) * SpeedFraction;
		P.Velocity = Back + FVector(Random.FRandRange(-14.0, 14.0), Random.FRandRange(-14.0, 14.0), Random.FRandRange(45.0, 170.0));
		P.Size0 = Random.FRandRange(5.0, 14.0);
		P.Size1 = Random.FRandRange(24.0, 64.0);
		P.Alpha = Random.FRandRange(0.45, 0.9);
		P.Spread = Ground.Z; // The ground height at birth, as the floor for the puff
		return;
	}
}

void ARoverEffects::Simulate(double Dt)
{
	const int32 Total = Particles.Num();
	TArray<FTransform> Transforms;
	Transforms.SetNumUninitialized(Total);
	DevilAge += Dt;
	DevilCenter += WindCmps * 1.6 * Dt; // The column drifts downwind
	if (DevilAge > 160.0)
	{
		DevilAge = 0.0;
		DevilCenter = Rover->GetActorLocation() + DevilOffsetCm;
	}
	DevilGroundTimer -= Dt;
	if (DevilGroundTimer <= 0.0)
	{
		DevilGroundTimer = 1.0;
		FHitResult Hit;
		if (GetWorld()->LineTraceSingleByObjectType(Hit, FVector(DevilCenter.X, DevilCenter.Y, 50000.0), FVector(DevilCenter.X, DevilCenter.Y, -50000.0), FCollisionObjectQueryParams(ECC_WorldStatic)))
		{
			DevilCenter.Z = Hit.ImpactPoint.Z;
		}
	}
	int32 AliveWheel = 0, AliveHaze = 0, AliveDevil = 0;
	const FTransform Hidden(FQuat::Identity, FVector(0.0, 0.0, -100000.0), FVector(0.001));
	for (int32 I = 0; I < Total; ++I)
	{
		FPuff& P = Particles[I];
		if (!P.bAlive)
		{
			Transforms[I] = Hidden;
			Puffs->SetCustomDataValue(I, 0, 0.0f, false);
			continue;
		}
		P.Age += Dt;
		if (P.Age >= P.Life)
		{
			if (P.Kind == EKind::Haze)
			{
				SpawnHaze(P, false);
			}
			else if (P.Kind == EKind::Devil)
			{
				SpawnDevil(P, false);
			}
			else
			{
				P.bAlive = false;
				Transforms[I] = Hidden;
				Puffs->SetCustomDataValue(I, 0, 0.0f, false);
				continue;
			}
		}
		const double T = P.Age / P.Life;
		switch (P.Kind)
		{
		case EKind::Wheel:
			++AliveWheel;
			// Mars's gravity, a little drag, and a pull toward the wind's speed sideways
			P.Velocity.Z -= MarsGravityCmps2 * Dt;
			P.Velocity *= FMath::Max(0.0, 1.0 - 0.5 * Dt);
			P.Velocity.X += (WindCmps.X * 0.7 - P.Velocity.X) * 1.1 * Dt;
			P.Velocity.Y += (WindCmps.Y * 0.7 - P.Velocity.Y) * 1.1 * Dt;
			P.Position += P.Velocity * Dt;
			if (P.Position.Z < P.Spread + 1.5)
			{
				P.Position.Z = P.Spread + 1.5; // Lands, and slides on with the wind
				P.Velocity.Z = 0.0;
			}
			break;
		case EKind::Haze:
			++AliveHaze;
			P.Position += (WindCmps * 3.0 + P.Velocity) * Dt;
			break;
		case EKind::Devil:
		{
			++AliveDevil;
			const double Height = P.Climb * P.Age;
			const double Radius = 110.0 + Height * 0.13 + P.Spread;
			const double Theta = P.Angle + P.Omega * P.Age;
			P.Position = DevilCenter + FVector(FMath::Cos(Theta) * Radius, FMath::Sin(Theta) * Radius, Height);
			break;
		}
		}
		const double Size = FMath::Lerp(P.Size0, P.Size1, T);
		const double FadeIn = FMath::Min(1.0, P.Age / FMath::Max(0.05, 0.12 * P.Life));
		const double FadeOut = P.Kind == EKind::Wheel ? FMath::Pow(1.0 - T, 1.3) : FMath::Sin(PI * T);
		Transforms[I] = FTransform(FQuat::Identity, P.Position, FVector(Size / 100.0)); // The sphere is 100 cm across
		Puffs->SetCustomDataValue(I, 0, static_cast<float>(P.Alpha * FadeIn * FadeOut), false);
	}
	Puffs->BatchUpdateInstancesTransforms(0, Transforms, true, true, true);

	LogTimer -= Dt;
	if (LogTimer <= 0.0)
	{
		LogTimer = 8.0;
		UE_LOG(LogRoverloom, Display, TEXT("Rover effects: puffs alive: wheel %d, haze %d, devil %d; ruts %d decals (made %d)"), AliveWheel, AliveHaze, AliveDevil, Decals.Num(), DecalsMade);
	}
}

void ARoverEffects::DropRuts(double Dt, const FTransform& Body, double SpeedMps)
{
	(void)Dt;
	(void)SpeedMps;
	for (int32 W = 0; W < RoverloomRover::NumWheels; ++W)
	{
		const FVector Wheel = Body.TransformPosition(RoverloomRover::WheelMountCm(W));
		FVector Ground;
		if (!GroundAt(Wheel.X, Wheel.Y, Ground) || Wheel.Z - Ground.Z > 55.0)
		{
			bHaveRut[W] = false; // Not rolling on the ground: no rut, and the next one starts fresh
			continue;
		}
		if (!bHaveRut[W])
		{
			LastRut[W] = Ground;
			bHaveRut[W] = true;
			continue;
		}
		FVector Delta = Ground - LastRut[W];
		Delta.Z = 0.0;
		const double Distance = Delta.Size();
		if (Distance > 300.0)
		{
			LastRut[W] = Ground; // A reset or a jump: no rut across it
			continue;
		}
		if (Distance < RutSpacingCm)
		{
			continue;
		}
		UDecalComponent* Decal = nullptr;
		if (Decals.Num() < MaxDecals)
		{
			Decal = NewObject<UDecalComponent>(this);
			Decal->SetupAttachment(GetRootComponent());
			Decal->RegisterComponent();
			Decals.Add(Decal);
		}
		else
		{
			Decal = Decals[NextDecal]; // The ring is full: the oldest rut is overwritten
		}
		NextDecal = (NextDecal + 1) % MaxDecals;
		++DecalsMade;
		const double Yaw = FMath::RadiansToDegrees(FMath::Atan2(Delta.Y, Delta.X));
		Decal->SetDecalMaterial(RutMaterial);
		// Projects straight down (local X), 12 cm deep each way; the width across the track, the length along it
		Decal->DecalSize = FVector(12.0, RutHalfWidthCm, 0.5 * RutLengthCm);
		Decal->SetWorldLocationAndRotation(0.5 * (Ground + LastRut[W]) + FVector(0.0, 0.0, 2.0), FRotator(-90.0, Yaw, 0.0));
		Decal->SetSortOrder(DecalsMade % 1000); // Later ruts lie on top of earlier ones
		Decal->FadeScreenSize = 0.0008f;
		LastRut[W] = Ground;
	}
}

void ARoverEffects::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (!Rover)
	{
		return;
	}
	const double Dt = FMath::Min<double>(DeltaSeconds, 0.1);
	const FRoverStatus& Status = Rover->GetStatus();
	const FTransform Body = Rover->GetActorTransform();
	const double Speed = FMath::Abs(Status.ForwardMps) + 0.6 * FMath::Abs(Status.YawRateRadps); // An effective rim speed, m/s
	if (bRuts)
	{
		DropRuts(Dt, Body, Speed);
	}
	if (bDust)
	{
		const double Fraction = FMath::Clamp(Speed / RoverloomRover::MaxSpeedMps, 0.0, 1.0);
		FVector Forward = Body.GetUnitAxis(EAxis::X);
		Forward.Z = 0.0;
		Forward = Forward.GetSafeNormal() * (Status.ForwardMps >= 0.0 ? 1.0 : -1.0);
		if (Fraction > 0.02 && Status.WheelsInContact >= 2)
		{
			for (int32 W = 0; W < RoverloomRover::NumWheels; ++W)
			{
				Carry[W] += 34.0 * Fraction * Dt; // Puffs per second per wheel at full speed
				const FVector Wheel = Body.TransformPosition(RoverloomRover::WheelMountCm(W));
				FVector Ground;
				const bool bGround = GroundAt(Wheel.X, Wheel.Y, Ground);
				while (Carry[W] >= 1.0)
				{
					Carry[W] -= 1.0;
					if (bGround && Wheel.Z - Ground.Z < 55.0)
					{
						EmitWheelDust(Ground, Forward, Fraction);
					}
				}
			}
		}
		Simulate(Dt);
	}
}
