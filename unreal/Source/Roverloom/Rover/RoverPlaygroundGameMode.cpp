#include "RoverPlaygroundGameMode.h"

#include "Components/DirectionalLightComponent.h"
#include "Components/SkyAtmosphereComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/DirectionalLight.h"
#include "Engine/ExponentialHeightFog.h"
#include "Engine/SkyLight.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "GameFramework/Controller.h"
#include "GameFramework/WorldSettings.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "PhysicalMaterials/PhysicalMaterial.h"

#include "../Roverloom.h"
#include "RoverDrive.h"
#include "RoverHud.h"
#include "RoverPawn.h"

namespace
{
	const double MarsGravityCmps2 = 371.0; // As WheelSpikeGameMode
	const int32 RockSeed = 7;
	const FLinearColor Regolith(0.42f, 0.24f, 0.14f);
	const FLinearColor Outcrop(0.33f, 0.2f, 0.13f);
	const FLinearColor Rock(0.25f, 0.17f, 0.12f);
}

ARoverPlaygroundGameMode::ARoverPlaygroundGameMode()
{
	DefaultPawnClass = nullptr; // The rover is spawned here, not at a player start
	HUDClass = ARoverHud::StaticClass();
}

void ARoverPlaygroundGameMode::StartPlay()
{
	AWorldSettings* Settings = GetWorld()->GetWorldSettings();
	Settings->bGlobalGravitySet = true;
	Settings->GlobalGravityZ = -MarsGravityCmps2;
	SpawnTerrain();
	SpawnLights();
	SpawnRover();
	Super::StartPlay();
	UE_LOG(LogRoverloom, Display, TEXT("Rover playground started, gravity %.3f, drive model P (provisional)"), GetWorld()->GetGravityZ());
	UE_LOG(LogRoverloom, Display, TEXT("Rover playground spawned: %d blocks (ground, step, 2 ramps, 2 plateaus, %d rocks), %d light actors, rover %s"),
		BlocksSpawned, RocksSpawned, LightsSpawned, Rover ? *Rover->GetName() : TEXT("missing"));
}

void ARoverPlaygroundGameMode::RestartPlayer(AController* NewPlayer)
{
	// Called when a player joins, which can be before StartPlay. The one rover is shared, and never respawned here.
	if (!NewPlayer)
	{
		return;
	}
	SpawnRover();
	NewPlayer->Possess(Rover);
}

void ARoverPlaygroundGameMode::SpawnRover()
{
	if (Rover)
	{
		return;
	}
	FActorSpawnParameters SpawnParams;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	Rover = GetWorld()->SpawnActor<ARoverPawn>(ARoverPawn::StaticClass(), FVector(0.0, 0.0, RoverloomRover::RideHeightCm),
		FRotator::ZeroRotator, SpawnParams);
}

AActor* ARoverPlaygroundGameMode::SpawnBlock(const FVector& Center, const FRotator& Rotation, const FVector& SizeCm,
	const FLinearColor& Color, const TCHAR* MeshPath)
{
	if (!GroundMaterial)
	{
		GroundMaterial = NewObject<UPhysicalMaterial>(this);
		GroundMaterial->Friction = RoverloomRover::Friction;
		GroundMaterial->StaticFriction = RoverloomRover::Friction;
		GroundMaterial->Restitution = 0.0f;
	}
	// As WheelSpikeGameMode::SpawnBlock: a movable cube, which the rig's WorldStatic sweeps hit.
	const FTransform Transform(Rotation, Center, SizeCm / 100.0);
	AStaticMeshActor* Block = GetWorld()->SpawnActorDeferred<AStaticMeshActor>(AStaticMeshActor::StaticClass(), Transform, nullptr,
		nullptr, ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
	UStaticMeshComponent* Mesh = Block->GetStaticMeshComponent();
	Mesh->SetMobility(EComponentMobility::Movable);
	Mesh->SetStaticMesh(LoadObject<UStaticMesh>(nullptr, MeshPath));
	Mesh->SetPhysMaterialOverride(GroundMaterial);
	Block->FinishSpawning(Transform);
	++BlocksSpawned;
	if (UMaterialInstanceDynamic* Material = Mesh->CreateDynamicMaterialInstance(0))
	{
		Material->SetVectorParameterValue(TEXT("Color"), Color);
	}
	return Block;
}

void ARoverPlaygroundGameMode::SpawnRamp(double StartXCm, double LaneYCm, double SlopeDeg, double LengthCm, double WidthCm,
	const FLinearColor& Color)
{
	// A tilted slab whose top surface starts at ground level at StartXCm and rises toward +X, then a plateau at the top.
	const double Theta = FMath::DegreesToRadians(SlopeDeg);
	const double HalfLength = LengthCm / 2.0;
	const double Thickness = 40.0;
	const double HalfThickness = Thickness / 2.0;
	const FVector Center(StartXCm + HalfLength * FMath::Cos(Theta) + HalfThickness * FMath::Sin(Theta), LaneYCm,
		HalfLength * FMath::Sin(Theta) - HalfThickness * FMath::Cos(Theta));
	SpawnBlock(Center, FRotator(SlopeDeg, 0.0, 0.0), FVector(LengthCm, WidthCm, Thickness), Color);
	const double TopCm = LengthCm * FMath::Sin(Theta);
	const double PlateauCm = 800.0;
	SpawnBlock(FVector(StartXCm + LengthCm * FMath::Cos(Theta) + PlateauCm / 2.0, LaneYCm, TopCm / 2.0), FRotator::ZeroRotator,
		FVector(PlateauCm, WidthCm, TopCm), Color);
}

void ARoverPlaygroundGameMode::SpawnTerrain()
{
	if (bTerrainSpawned)
	{
		return;
	}
	bTerrainSpawned = true;
	// 200 m square, top at z = 0, as phase C's ground.
	SpawnBlock(FVector(0.0, 0.0, -50.0), FRotator::ZeroRotator, FVector(20000.0, 20000.0, 100.0), Regolith);
	// Straight ahead: a 25 cm step, half a wheel diameter, as phase C's cstep_25.
	SpawnBlock(FVector(1500.0, 0.0, 12.5), FRotator::ZeroRotator, FVector(600.0, 800.0, 25.0), Outcrop);
	// Unreal +Y is to the rover's right at the start. 10 degrees on the right, 15 on the left.
	SpawnRamp(600.0, 1500.0, 10.0, 1200.0, 600.0, Outcrop);
	SpawnRamp(600.0, -1500.0, 15.0, 1200.0, 600.0, Outcrop);
	// Rocks behind the start, with a fixed seed, kept out of the test lanes.
	FRandomStream Random(RockSeed);
	for (int32 Index = 0; Index < 24; ++Index)
	{
		const FVector Center(Random.FRandRange(-6000.0, -800.0), Random.FRandRange(-4000.0, 4000.0), 0.0);
		const double Size = Random.FRandRange(20.0, 120.0);
		const FVector Scale(Size * Random.FRandRange(0.8, 1.6), Size * Random.FRandRange(0.8, 1.4), Size * Random.FRandRange(0.4, 0.8));
		SpawnBlock(Center, FRotator(0.0, Random.FRandRange(0.0, 360.0), 0.0), Scale, Rock, TEXT("/Engine/BasicShapes/Sphere.Sphere"));
		++RocksSpawned;
	}
}

void ARoverPlaygroundGameMode::SpawnLights()
{
	UWorld* World = GetWorld();
	FActorSpawnParameters SpawnParams;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

	// Sun 20 degrees up, behind and to the left of the rover's start, as shot 1. Movable, since nothing is baked.
	const FTransform SunTransform(FRotator(-20.0, 45.0, 0.0));
	ADirectionalLight* Sun = World->SpawnActorDeferred<ADirectionalLight>(ADirectionalLight::StaticClass(), SunTransform, nullptr,
		nullptr, ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
	// ADirectionalLight::GetComponent is editor-only; ALight::GetLightComponent exists in every build.
	Sun->GetLightComponent()->SetMobility(EComponentMobility::Movable);
	Sun->FinishSpawning(SunTransform);
	if (UDirectionalLightComponent* SunLight = Cast<UDirectionalLightComponent>(Sun->GetLightComponent()))
	{
		SunLight->SetAtmosphereSunLight(true);
	}

	World->SpawnActor<ASkyAtmosphere>(ASkyAtmosphere::StaticClass(), FTransform::Identity, SpawnParams);

	ASkyLight* Sky = World->SpawnActorDeferred<ASkyLight>(ASkyLight::StaticClass(), FTransform::Identity, nullptr, nullptr,
		ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
	Sky->GetLightComponent()->SetMobility(EComponentMobility::Movable);
	Sky->GetLightComponent()->SetRealTimeCapture(true);
	Sky->FinishSpawning(FTransform::Identity);

	World->SpawnActor<AExponentialHeightFog>(AExponentialHeightFog::StaticClass(), FTransform::Identity, SpawnParams);
	LightsSpawned = 4; // Sun, sky atmosphere, sky light, fog
}
