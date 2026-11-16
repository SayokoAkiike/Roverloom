#include "RoverPlaygroundGameMode.h"

#include "Components/DirectionalLightComponent.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Engine/CollisionProfile.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Components/SkyAtmosphereComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/DirectionalLight.h"
#include "Engine/ExponentialHeightFog.h"
#include "Engine/PostProcessVolume.h"
#include "HAL/IConsoleManager.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Engine/SkyLight.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Controller.h"
#include "LandscapeProxy.h"
#include "GameFramework/WorldSettings.h"
#include "PhysicalMaterials/PhysicalMaterial.h"

#include "../Roverloom.h"
#include "Greybox.h"
#include "RoverDrive.h"
#include "RoverHud.h"
#include "RoverPawn.h"

namespace
{
	const double MarsGravityCmps2 = 371.0; // As WheelSpikeGameMode
	const int32 RockSeed = 7;
	// mars_inspired palette matched to V1's dusty sky: rust regolith, darker basaltic outcrops and rocks, so the step,
	// ramps, and rocks read against the ground.
	const FLinearColor Regolith(0.46f, 0.21f, 0.10f);
	const FLinearColor Outcrop(0.17f, 0.11f, 0.08f);
	const FLinearColor Rock(0.13f, 0.09f, 0.07f);
	const int32 FarRockSeed = 11;
	const int32 ScatterSeed = 20261116; // Gale rock scatter
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
	BindLandscape();
	ApplyProfile();
	SpawnTerrain();
	SpawnLights();
	SpawnRover();
	SpawnScatter();
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

void ARoverPlaygroundGameMode::SpawnScatter()
{
	// Rocks for the Gale level: four Poly Haven meshes (see docs/assets-and-sources.md) as instances, with a fixed seed. They are
	// visual only: no collision, no physics, so the rover's drive does not depend on them. They are kept off the straight test
	// lane ahead of the start and out of a circle around it. Without the meshes (they live outside Git) nothing is placed.
	if (!bHasLandscape)
	{
		return;
	}
	int32 Enabled = 1;
	FParse::Value(FCommandLine::Get(), TEXT("RoverRocks="), Enabled);
	if (Enabled == 0)
	{
		return;
	}
	struct FKind
	{
		const TCHAR* Path;
		double MinScale;
		double MaxScale;
		double Share;
		float CullCm;  // Not drawn beyond this distance. Small rocks are not worth drawing far away
		bool bShadow;  // Whether it casts a shadow. Lumen's scene and the shadow pass are where 1,140 rocks cost the most
	};
	static const FKind Kinds[] = {
		{TEXT("/Game/Licensed/PolyHaven/rock_09/rock_09_1k.rock_09_1k"), 1.5, 7.0, 0.55, 5000.0f, false},                                     // Pebbles, 10 to 50 cm
		{TEXT("/Game/Licensed/PolyHaven/namaqualand_boulder_06/namaqualand_boulder_06_1k.namaqualand_boulder_06_1k"), 0.35, 1.7, 0.25, 15000.0f, true}, // 25 cm to 1.1 m
		{TEXT("/Game/Licensed/PolyHaven/namaqualand_boulder_02/namaqualand_boulder_02_1k.namaqualand_boulder_02_1k"), 0.12, 0.5, 0.12, 30000.0f, true}, // 30 cm to 1.3 m
		{TEXT("/Game/Licensed/PolyHaven/namaqualand_boulder_04/namaqualand_boulder_04_1k.namaqualand_boulder_04_1k"), 0.10, 0.4, 0.08, 30000.0f, true}, // 25 cm to 1.0 m
	};
	UWorld* World = GetWorld();
	AActor* Holder = World->SpawnActor<AActor>();
	USceneComponent* Root = NewObject<USceneComponent>(Holder, TEXT("RockRoot"));
	Holder->SetRootComponent(Root);
	Root->RegisterComponent();
	Holder->SetActorLabel(TEXT("GaleRocks"));

	TArray<UHierarchicalInstancedStaticMeshComponent*> Components;
	for (const FKind& Kind : Kinds)
	{
		UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, Kind.Path, nullptr, LOAD_NoWarn | LOAD_Quiet);
		if (!Mesh)
		{
			UE_LOG(LogRoverloom, Display, TEXT("Rock scatter: %s not found (the Poly Haven rocks are outside Git); none placed"), Kind.Path);
			Holder->Destroy();
			return;
		}
		UHierarchicalInstancedStaticMeshComponent* Component = NewObject<UHierarchicalInstancedStaticMeshComponent>(Holder);
		Component->SetupAttachment(Root);
		Component->SetStaticMesh(Mesh);
		Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Component->SetCollisionProfileName(UCollisionProfile::NoCollision_ProfileName);
		Component->SetCanEverAffectNavigation(false);
		Component->SetCullDistances(0, static_cast<int32>(Kind.CullCm));
		Component->SetCastShadow(Kind.bShadow);
		Component->bAffectDistanceFieldLighting = false; // Kept out of Lumen's scene: decoration, not lighting
		Component->bAffectDynamicIndirectLighting = false;
		Component->RegisterComponent();
		Components.Add(Component);
	}

	FRandomStream Random(ScatterSeed);
	TArray<TArray<FTransform>> Placed;
	Placed.SetNum(Components.Num());
	auto Forbidden = [](double X, double Y)
	{
		const bool bLane = X > -300.0 && X < 4200.0 && FMath::Abs(Y) < 450.0; // The straight lane: 3 m behind to 42 m ahead, 9 m wide
		const bool bStart = X * X + Y * Y < 800.0 * 800.0;                      // And 8 m around the start
		return bLane || bStart;
	};
	const struct { int32 Count; double MinR; double MaxR; } Zones[] = {{350, 800.0, 6000.0}, {350, 6000.0, 40000.0}};
	int32 Total = 0;
	for (const auto& Zone : Zones)
	{
		for (int32 Index = 0; Index < Zone.Count; ++Index)
		{
			// Uniform over the ring's area
			const double R = FMath::Sqrt(Random.FRandRange(Zone.MinR * Zone.MinR, Zone.MaxR * Zone.MaxR));
			const double Angle = Random.FRandRange(0.0, 2.0 * PI);
			const double X = R * FMath::Cos(Angle);
			const double Y = R * FMath::Sin(Angle);
			const double PickKind = Random.FRand();
			const double SizeDraw = Random.FRand();
			const double Yaw = Random.FRandRange(0.0, 360.0);
			const double Tilt1 = Random.FRandRange(-10.0, 10.0);
			const double Tilt2 = Random.FRandRange(-10.0, 10.0);
			if (Forbidden(X, Y))
			{
				continue; // The draws above are still consumed, so the layout elsewhere does not depend on the lane
			}
			int32 Chosen = 0;
			double Cumulative = 0.0;
			for (int32 K = 0; K < UE_ARRAY_COUNT(Kinds); ++K)
			{
				Cumulative += Kinds[K].Share;
				if (PickKind <= Cumulative)
				{
					Chosen = K;
					break;
				}
			}
			FHitResult Hit;
			if (!World->LineTraceSingleByObjectType(Hit, FVector(X, Y, 50000.0), FVector(X, Y, -50000.0), FCollisionObjectQueryParams(ECC_WorldStatic)))
			{
				continue; // Off the site Landscape
			}
			// Few large, many small: the size grows with the cube of the draw
			const double Scale = Kinds[Chosen].MinScale + (Kinds[Chosen].MaxScale - Kinds[Chosen].MinScale) * SizeDraw * SizeDraw * SizeDraw;
			Placed[Chosen].Add(FTransform(FRotator(Tilt1, Yaw, Tilt2), Hit.ImpactPoint - FVector(0.0, 0.0, 6.0 * Scale), FVector(Scale)));
			++Total;
		}
	}
	for (int32 K = 0; K < Components.Num(); ++K)
	{
		Components[K]->AddInstances(Placed[K], false, true);
	}
	RocksSpawned += Total;
	UE_LOG(LogRoverloom, Display, TEXT("Rock scatter: %d instances (seed %d), no collision, off the test lane"), Total, ScatterSeed);
}

void ARoverPlaygroundGameMode::ApplyProfile()
{
	// -RoverProfile=dev|capture. Only rendering settings: no physics, collision, or drive value is touched here.
	// dev: software Lumen for GI and reflections, with the rest as the project has it. capture: the highest settings the Mac
	// has completed in a run, and it may run far below real time. Neither is the project default for the editor.
	FString Profile = TEXT("");
	if (!FParse::Value(FCommandLine::Get(), TEXT("RoverProfile="), Profile))
	{
		return;
	}
	auto Set = [](const TCHAR* Name, const TCHAR* Value)
	{
		if (IConsoleVariable* Variable = IConsoleManager::Get().FindConsoleVariable(Name))
		{
			Variable->Set(Value, ECVF_SetByCode);
		}
		else
		{
			UE_LOG(LogRoverloom, Warning, TEXT("Render profile: console variable %s does not exist"), Name);
		}
	};
	Set(TEXT("r.DynamicGlobalIlluminationMethod"), TEXT("1")); // Lumen
	Set(TEXT("r.ReflectionMethod"), TEXT("1"));                // Lumen reflections
	Set(TEXT("r.Lumen.HardwareRayTracing"), TEXT("0"));        // Software Lumen: no hardware ray tracing on this Mac
	if (Profile == TEXT("capture"))
	{
		Set(TEXT("r.Shadow.Virtual.Enable"), TEXT("1"));
		Set(TEXT("r.Lumen.ScreenProbeGather.DownsampleFactor"), TEXT("8"));
		Set(TEXT("r.Lumen.ScreenProbeGather.TracingOctahedronResolution"), TEXT("16"));
		Set(TEXT("r.Lumen.Reflections.DownsampleFactor"), TEXT("1"));
		Set(TEXT("r.Lumen.TraceMeshSDFs"), TEXT("1"));
		Set(TEXT("r.ScreenPercentage"), TEXT("100"));
		Set(TEXT("r.MotionBlurQuality"), TEXT("0"));
	}
	UE_LOG(LogRoverloom, Display, TEXT("Rover render profile '%s' applied"), *Profile);
}

void ARoverPlaygroundGameMode::BindLandscape()
{
	// A level with a Landscape (the Gale level) replaces the greybox ground and its test lanes. The Landscape is given the
	// same physical material as the blocks, so friction and restitution are the rover's existing values.
	if (bLandscapeChecked)
	{
		return;
	}
	bLandscapeChecked = true;
	for (TActorIterator<ALandscapeProxy> It(GetWorld()); It; ++It)
	{
		if (!GroundMaterial)
		{
			GroundMaterial = NewObject<UPhysicalMaterial>(this);
			GroundMaterial->Friction = RoverloomRover::Friction;
			GroundMaterial->StaticFriction = RoverloomRover::Friction;
			GroundMaterial->Restitution = 0.0f;
		}
		It->DefaultPhysMaterial = GroundMaterial;
		It->RecreateCollisionComponents();
		bTerrainSpawned = true;
		bHasLandscape = true;
	}
}

void ARoverPlaygroundGameMode::SpawnRover()
{
	if (Rover)
	{
		return;
	}
	BindLandscape();
	FActorSpawnParameters SpawnParams;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	// The site origin is at z = 0 on the greybox ground; on a Landscape it is the ground found straight below the origin.
	double GroundCm = 0.0;
	if (bHasLandscape)
	{
		FHitResult Hit;
		// By object type, so that a spectator pawn at the origin is not mistaken for ground
		if (GetWorld()->LineTraceSingleByObjectType(Hit, FVector(0.0, 0.0, 50000.0), FVector(0.0, 0.0, -50000.0), FCollisionObjectQueryParams(ECC_WorldStatic)))
		{
			GroundCm = Hit.ImpactPoint.Z;
			UE_LOG(LogRoverloom, Display, TEXT("Rover start trace hit %s on %s"), Hit.GetActor() ? *Hit.GetActor()->GetActorLabel() : TEXT("none"), Hit.GetComponent() ? *Hit.GetComponent()->GetName() : TEXT("none"));
		}
		UE_LOG(LogRoverloom, Display, TEXT("Rover start on the Landscape: ground at z %.1f cm"), GroundCm);
	}
	Rover = GetWorld()->SpawnActor<ARoverPawn>(ARoverPawn::StaticClass(), FVector(0.0, 0.0, GroundCm + RoverloomRover::RideHeightCm),
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
	RoverloomGreybox::Paint(Mesh, Color, 0.9f); // Matte regolith and rock
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
		SpawnBlock(Center, FRotator(0.0, Random.FRandRange(0.0, 360.0), 0.0), Scale, Rock * Random.FRandRange(0.8f, 1.25f),
			TEXT("/Engine/BasicShapes/Sphere.Sphere"));
		++RocksSpawned;
	}
	// Rocks in the view ahead, beyond every test lane (the step ends at x 18 m, the ramps' plateaus at x 25.6 m).
	FRandomStream Far(FarRockSeed);
	for (int32 Index = 0; Index < 36; ++Index)
	{
		const FVector Center(Far.FRandRange(3000.0, 8000.0), Far.FRandRange(-4500.0, 4500.0), 0.0);
		const double Size = Far.FRandRange(25.0, 160.0);
		const FVector Scale(Size * Far.FRandRange(0.8, 1.6), Size * Far.FRandRange(0.8, 1.4), Size * Far.FRandRange(0.4, 0.8));
		SpawnBlock(Center, FRotator(0.0, Far.FRandRange(0.0, 360.0), 0.0), Scale, Rock * Far.FRandRange(0.8f, 1.25f),
			TEXT("/Engine/BasicShapes/Sphere.Sphere"));
		++RocksSpawned;
	}
}

void ARoverPlaygroundGameMode::SpawnLights()
{
	UWorld* World = GetWorld();
	FActorSpawnParameters SpawnParams;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

	// Light presets, chosen with -RoverLight=noon|afternoon|sunset. Sun height above the horizon, sun strength, and the fixed
	// exposure of the camera (as a camera would have it: the same for the whole run). Values were set by eye. They are
	// artistic presets, not a model of the real sky. The default is the original 20 degrees.
	FString Preset = TEXT("default");
	FParse::Value(FCommandLine::Get(), TEXT("RoverLight="), Preset);
	double SunElevationDeg = 20.0;
	float SunLux = 10.0f;
	FLinearColor SunColor(1.0f, 0.96f, 0.90f); // Slightly warm white; the dusty sky does the rest
	float MieScale = 0.02f;
	float ExposureEv = 0.0f;
	bool bFixedExposure = true;
	if (Preset == TEXT("noon"))
	{
		SunElevationDeg = 58.0;
		SunLux = 4.3f; // Mars gets about 43% of the sunlight Earth does
		ExposureEv = 10.5f;
	}
	else if (Preset == TEXT("afternoon"))
	{
		SunElevationDeg = 22.0;
		SunLux = 4.3f;
		ExposureEv = 11.3f;
	}
	else if (Preset == TEXT("sunset"))
	{
		SunElevationDeg = 2.5;
		SunLux = 2.2f;
		ExposureEv = 11.4f;
		SunColor = FLinearColor(1.0f, 0.55f, 0.30f); // The sun's light has crossed a long path of dust
		MieScale = 0.06f; // More dust in the air, as on a hazy evening
	}
	else
	{
		bFixedExposure = false; // The original look, with the engine's own exposure
	}
	if (FParse::Value(FCommandLine::Get(), TEXT("RoverExposure="), ExposureEv))
	{
		bFixedExposure = true; // -RoverExposure=EV overrides the preset's value, for tuning
	}
	// Sun behind and to the left of the rover's start, as shot 1. Movable, since nothing is baked.
	const FTransform SunTransform(FRotator(-SunElevationDeg, 45.0, 0.0));
	ADirectionalLight* Sun = World->SpawnActorDeferred<ADirectionalLight>(ADirectionalLight::StaticClass(), SunTransform, nullptr,
		nullptr, ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
	// ADirectionalLight::GetComponent is editor-only; ALight::GetLightComponent exists in every build.
	Sun->GetLightComponent()->SetMobility(EComponentMobility::Movable);
	Sun->FinishSpawning(SunTransform);
	if (UDirectionalLightComponent* SunLight = Cast<UDirectionalLightComponent>(Sun->GetLightComponent()))
	{
		SunLight->SetAtmosphereSunLight(true);
		SunLight->SetLightColor(SunColor);
		if (Preset != TEXT("default"))
		{
			SunLight->SetIntensity(SunLux);
		}
	}
	if (bFixedExposure)
	{
		// One unbound volume with manual exposure, so that the shot does not brighten or darken as the view changes.
		APostProcessVolume* Exposure = World->SpawnActor<APostProcessVolume>(APostProcessVolume::StaticClass(), FTransform::Identity, SpawnParams);
		Exposure->bUnbound = true;
		Exposure->Settings.bOverride_AutoExposureMethod = true;
		Exposure->Settings.AutoExposureMethod = EAutoExposureMethod::AEM_Manual;
		Exposure->Settings.bOverride_AutoExposureBias = true;
		Exposure->Settings.AutoExposureBias = ExposureEv;
		UE_LOG(LogRoverloom, Display, TEXT("Rover light preset '%s': sun %.1f deg above the horizon, %.1f lux, fixed exposure %.1f"), *Preset, SunElevationDeg, SunLux, ExposureEv);
	}

	// A Mars-inspired sky (mars_inspired: an artistic preset, not a validated atmosphere model): Mars's radius, a thin
	// CO2 atmosphere with little Rayleigh scattering, and suspended dust that scatters warm light and absorbs blue,
	// so the daytime sky turns butterscotch instead of blue. Values chosen by eye against the greybox.
	// Set through the component's setters after spawning: assigning the fields directly before FinishSpawning did not
	// reach the renderer (measured 2026-11-07: two different presets rendered the same sky).
	ASkyAtmosphere* Atmosphere = World->SpawnActor<ASkyAtmosphere>(ASkyAtmosphere::StaticClass(), FTransform::Identity, SpawnParams);
	if (USkyAtmosphereComponent* Air = Atmosphere ? Atmosphere->FindComponentByClass<USkyAtmosphereComponent>() : nullptr)
	{
		Air->SetBottomRadius(3389.5f);   // km
		Air->SetAtmosphereHeight(80.0f); // km
		Air->SetGroundAlbedo(FColor(170, 110, 70));
		Air->SetRayleighScatteringScale(0.0005f);
		Air->SetRayleighExponentialDistribution(11.0f); // km, Mars's scale height
		Air->SetMieScatteringScale(MieScale);
		Air->SetMieScattering(FLinearColor(0.95f, 0.60f, 0.32f));
		Air->SetMieAbsorptionScale(0.006f);
		Air->SetMieAbsorption(FLinearColor(0.35f, 0.55f, 0.75f));
		Air->SetMieAnisotropy(0.5f);
		Air->SetMieExponentialDistribution(11.0f);
	}

	ASkyLight* Sky = World->SpawnActorDeferred<ASkyLight>(ASkyLight::StaticClass(), FTransform::Identity, nullptr, nullptr,
		ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
	Sky->GetLightComponent()->SetMobility(EComponentMobility::Movable);
	Sky->GetLightComponent()->SetRealTimeCapture(true);
	Sky->FinishSpawning(FTransform::Identity);

	AExponentialHeightFog* Fog = World->SpawnActor<AExponentialHeightFog>(AExponentialHeightFog::StaticClass(), FTransform::Identity, SpawnParams);
	if (UExponentialHeightFogComponent* FogComponent = Fog ? Fog->FindComponentByClass<UExponentialHeightFogComponent>() : nullptr)
	{
		if (bHasLandscape)
		{
			// Distance haze for the Gale level: nothing within 400 m, then a cool blue-grey that thickens with distance, so
			// the ridges of the horizon Landscape recede. A chosen look (the owner asked for a bluish haze). Mars's own
			// daytime dust haze is butterscotch, and its blue is a glow near the sun at sunset, so this is not a measurement.
			FogComponent->SetFogInscatteringColor(FLinearColor(0.42f, 0.50f, 0.64f));
			FogComponent->SetFogDensity(0.004f);
			FogComponent->SetFogHeightFalloff(0.25f);
			FogComponent->SetStartDistance(40000.0f);
			FogComponent->SetFogMaxOpacity(0.92f);
		}
		else
		{
			FogComponent->SetFogInscatteringColor(FLinearColor(0.55f, 0.38f, 0.25f)); // Dust haze toward the horizon
			FogComponent->SetFogDensity(0.01f); // Half the default, so the horizon and shadows stay readable
		}
	}
	LightsSpawned = 4; // Sun, sky atmosphere, sky light, fog
}
