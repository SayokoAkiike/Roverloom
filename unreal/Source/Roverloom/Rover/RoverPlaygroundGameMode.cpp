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
#include "../Bridge/Frames.h"
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
	// Rocks and pebbles for the Gale level, as instanced Poly Haven meshes (see docs/assets-and-sources.md) with a fixed seed.
	// Sizes follow a bounded power law, so there are very many small stones and few large rocks: the radius runs from 3 cm to
	// 1.5 m, and the number larger than r falls as r^-1.9. Each one has a random yaw, tilt, and slightly squashed scale, and sits
	// half buried: the middle of its bounds is put on the ground. They are visual only: no collision, no physics, so the rover's
	// drive does not depend on them. They are kept off the straight test lane ahead of the start and out of a circle around it.
	// Without the meshes (they live outside Git) nothing is placed. -RoverRocks=0 turns them off; -RoverRockScale=N sets the
	// count to N percent, for measuring cost.
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
	int32 CountPercent = 100;
	FParse::Value(FCommandLine::Get(), TEXT("RoverRockScale="), CountPercent);
	int32 CullPercent = 100; // -RoverRockCull=N scales every draw distance, for measuring cost
	FParse::Value(FCommandLine::Get(), TEXT("RoverRockCull="), CullPercent);
	int32 Shadows = 1; // -RoverRockShadows=0 turns off every rock shadow
	FParse::Value(FCommandLine::Get(), TEXT("RoverRockShadows="), Shadows);

	static const TCHAR* MeshPaths[] = {
		TEXT("/Game/Licensed/PolyHaven/rock_09/rock_09_1k.rock_09_1k"),
		TEXT("/Game/Licensed/PolyHaven/namaqualand_boulder_06/namaqualand_boulder_06_1k.namaqualand_boulder_06_1k"),
		TEXT("/Game/Licensed/PolyHaven/namaqualand_boulder_02/namaqualand_boulder_02_1k.namaqualand_boulder_02_1k"),
		TEXT("/Game/Licensed/PolyHaven/namaqualand_boulder_04/namaqualand_boulder_04_1k.namaqualand_boulder_04_1k"),
	};
	constexpr int32 MeshCount = UE_ARRAY_COUNT(MeshPaths);
	UStaticMesh* Meshes[MeshCount] = {};
	double BaseRadiusCm[MeshCount] = {};
	FVector LocalCenter[MeshCount];
	for (int32 M = 0; M < MeshCount; ++M)
	{
		Meshes[M] = LoadObject<UStaticMesh>(nullptr, MeshPaths[M], nullptr, LOAD_NoWarn | LOAD_Quiet);
		if (!Meshes[M])
		{
			UE_LOG(LogRoverloom, Display, TEXT("Rock scatter: %s not found (the Poly Haven rocks are outside Git); none placed"), MeshPaths[M]);
			return;
		}
		const FBoxSphereBounds Bounds = Meshes[M]->GetBounds();
		BaseRadiusCm[M] = 0.5 * (Bounds.BoxExtent.X + Bounds.BoxExtent.Y);
		LocalCenter[M] = Bounds.Origin;
	}

	UWorld* World = GetWorld();
	AActor* Holder = World->SpawnActor<AActor>();
	USceneComponent* Root = NewObject<USceneComponent>(Holder, TEXT("RockRoot"));
	Holder->SetRootComponent(Root);
	Root->RegisterComponent();
	Holder->SetActorLabel(TEXT("GaleRocks"));

	// One instanced component per mesh and size class. Small stones are not drawn far away and cast no shadow, and nothing here
	// enters Lumen's scene: it is decoration, not lighting.
	struct FClass
	{
		double MaxRadiusM;
		float CullCm;
		bool bShadow;
	};
	static const FClass Classes[] = {{0.06, 450.0f, false}, {0.15, 900.0f, false}, {0.40, 2200.0f, false}, {0.90, 7000.0f, true}, {1.6, 20000.0f, true}};
	constexpr int32 ClassCount = UE_ARRAY_COUNT(Classes);
	TMap<int32, UHierarchicalInstancedStaticMeshComponent*> Components;
	TMap<int32, TArray<FTransform>> Placed;
	auto ComponentFor = [&](int32 Mesh, int32 Class)
	{
		const int32 Key = Mesh * ClassCount + Class;
		if (UHierarchicalInstancedStaticMeshComponent** Found = Components.Find(Key))
		{
			return *Found;
		}
		UHierarchicalInstancedStaticMeshComponent* Component = NewObject<UHierarchicalInstancedStaticMeshComponent>(Holder);
		Component->SetupAttachment(Root);
		Component->SetStaticMesh(Meshes[Mesh]);
		Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Component->SetCollisionProfileName(UCollisionProfile::NoCollision_ProfileName);
		Component->SetCanEverAffectNavigation(false);
		Component->SetCullDistances(0, static_cast<int32>(Classes[Class].CullCm * CullPercent / 100.0f));
		Component->SetCastShadow(Classes[Class].bShadow && Shadows != 0);
		Component->bAffectDistanceFieldLighting = false;
		Component->bAffectDynamicIndirectLighting = false;
		Component->RegisterComponent();
		Components.Add(Key, Component);
		return Component;
	};

	auto Forbidden = [](double X, double Y)
	{
		const bool bLane = X > -300.0 && X < 4200.0 && FMath::Abs(Y) < 250.0; // The straight lane: 3 m behind to 42 m ahead, 5 m wide
		const bool bStart = X * X + Y * Y < 300.0 * 300.0;                      // And 3 m around the start
		return bLane || bStart;
	};

	constexpr double Alpha = 1.9;     // Cumulative number larger than r falls as r^-Alpha
	constexpr double MaxRadiusM = 1.5;
	const struct { int32 Count; double MinR; double MaxR; double MinRadiusM; } Zones[] = {
		{12000, 300.0, 1200.0, 0.03},     // Near: 3 to 12 m around the start, down to 3 cm
		{14000, 1200.0, 6000.0, 0.06},    // Mid: 12 to 60 m
		{8000, 6000.0, 42000.0, 0.15},    // Far: to 420 m, small stones would not show
	};
	FRandomStream Random(ScatterSeed);
	int32 Total = 0;
	int32 BySize[ClassCount] = {};
	double SmallestM = 1e9;
	double LargestM = 0.0;
	for (const auto& Zone : Zones)
	{
		const int32 Count = Zone.Count * FMath::Clamp(CountPercent, 0, 400) / 100;
		const double Tail = 1.0 - FMath::Pow(Zone.MinRadiusM / MaxRadiusM, Alpha);
		for (int32 Index = 0; Index < Count; ++Index)
		{
			// Every draw is made before any rejection, so the layout elsewhere does not depend on the lane
			const double Ring = FMath::Sqrt(Random.FRandRange(Zone.MinR * Zone.MinR, Zone.MaxR * Zone.MaxR));
			const double Angle = Random.FRandRange(0.0, 2.0 * PI);
			const double SizeDraw = Random.FRand();
			const double MeshDraw = Random.FRand();
			const double Yaw = Random.FRandRange(0.0, 360.0);
			const double Pitch = Random.FRandRange(-15.0, 15.0);
			const double Roll = Random.FRandRange(-15.0, 15.0);
			const double Squash = Random.FRandRange(0.5, 0.95);
			const double Stretch = Random.FRandRange(0.8, 1.3);
			const double X = Ring * FMath::Cos(Angle);
			const double Y = Ring * FMath::Sin(Angle);
			if (Forbidden(X, Y))
			{
				continue;
			}
			// Bounded Pareto, by inverting its distribution
			const double RadiusM = Zone.MinRadiusM * FMath::Pow(1.0 - SizeDraw * Tail, -1.0 / Alpha);
			int32 Class = 0;
			while (Class < ClassCount - 1 && RadiusM > Classes[Class].MaxRadiusM)
			{
				++Class;
			}
			// Small stones borrow every shape; big ones only the big boulders
			int32 Mesh;
			if (RadiusM < 0.12)
			{
				Mesh = MeshDraw < 0.6 ? 0 : (MeshDraw < 0.85 ? 1 : (MeshDraw < 0.93 ? 2 : 3));
			}
			else if (RadiusM < 0.5)
			{
				Mesh = MeshDraw < 0.5 ? 1 : (MeshDraw < 0.7 ? 0 : (MeshDraw < 0.85 ? 2 : 3));
			}
			else
			{
				Mesh = MeshDraw < 0.4 ? 2 : (MeshDraw < 0.8 ? 3 : 1);
			}
			FHitResult Hit;
			if (!World->LineTraceSingleByObjectType(Hit, FVector(X, Y, 50000.0), FVector(X, Y, -50000.0), FCollisionObjectQueryParams(ECC_WorldStatic)))
			{
				continue; // Off the site Landscape
			}
			const double Scale = RadiusM * 100.0 / BaseRadiusCm[Mesh];
			const FVector Scale3(Scale * Stretch, Scale / Stretch, Scale * Squash);
			const FRotator Rotation(Pitch, Yaw, Roll);
			// Half buried: the middle of the mesh's bounds is put on the ground
			const FVector Location = Hit.ImpactPoint - Rotation.RotateVector(Scale3 * LocalCenter[Mesh]);
			Placed.FindOrAdd(Mesh * ClassCount + Class).Add(FTransform(Rotation, Location, Scale3));
			++Total;
			++BySize[Class];
			SmallestM = FMath::Min(SmallestM, RadiusM);
			LargestM = FMath::Max(LargestM, RadiusM);
		}
	}
	for (TPair<int32, TArray<FTransform>>& Pair : Placed)
	{
		ComponentFor(Pair.Key / ClassCount, Pair.Key % ClassCount)->AddInstances(Pair.Value, false, true);
	}
	RocksSpawned += Total;
	UE_LOG(LogRoverloom, Display, TEXT("Rock scatter: %d instances (seed %d), radius %.3f to %.2f m, by class (to 6, 15, 40, 90 cm, larger) %d %d %d %d %d, no collision, off the test lane"),
		Total, ScatterSeed, SmallestM, LargestM, BySize[0], BySize[1], BySize[2], BySize[3], BySize[4]);
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
	if (Profile == TEXT("dev"))
	{
		Set(TEXT("r.AntiAliasingMethod"), TEXT("3")); // TAA: about 2.5 ms cheaper than TSR at 1280 x 720 on this Mac (measured)
	}
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
	// -RoverStartM=east,north starts the rover elsewhere on the Landscape (site frame, meters), to look at other ground. Only for
	// viewing: the mission link and the scenarios assume the origin.
	FVector StartCm = FVector::ZeroVector;
	FString StartText;
	if (bHasLandscape && FParse::Value(FCommandLine::Get(), TEXT("RoverStartM="), StartText, false)) // false: do not stop at the comma
	{
		TArray<FString> Parts;
		StartText.ParseIntoArray(Parts, TEXT(","));
		if (Parts.Num() >= 2)
		{
			StartCm = RoverloomFrames::SiteToUnrealPosition(FVector(FCString::Atod(*Parts[0]), FCString::Atod(*Parts[1]), 0.0));
		}
	}
	if (bHasLandscape)
	{
		FHitResult Hit;
		// By object type, so that a spectator pawn at the origin is not mistaken for ground
		if (GetWorld()->LineTraceSingleByObjectType(Hit, FVector(StartCm.X, StartCm.Y, 50000.0), FVector(StartCm.X, StartCm.Y, -50000.0), FCollisionObjectQueryParams(ECC_WorldStatic)))
		{
			GroundCm = Hit.ImpactPoint.Z;
			UE_LOG(LogRoverloom, Display, TEXT("Rover start trace hit %s on %s"), Hit.GetActor() ? *Hit.GetActor()->GetActorLabel() : TEXT("none"), Hit.GetComponent() ? *Hit.GetComponent()->GetName() : TEXT("none"));
		}
		UE_LOG(LogRoverloom, Display, TEXT("Rover start on the Landscape: ground at z %.1f cm"), GroundCm);
	}
	Rover = GetWorld()->SpawnActor<ARoverPawn>(ARoverPawn::StaticClass(), FVector(StartCm.X, StartCm.Y, GroundCm + RoverloomRover::RideHeightCm),
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

	// Light presets, chosen with -RoverLight=noon|afternoon|sunset. Each is a whole look: where the sun is and what color its light
	// is, what the dust in the air does to the sky, the haze, the sky light, and the fixed exposure of the camera (the same for the
	// whole run, as a camera would have it). Values were set by eye against renders. They are artistic presets (mars_inspired), not
	// a model of the real sky. The default, without -RoverLight, is the original look.
	struct FLook
	{
		double SunElevationDeg;
		double SunYawDeg;     // The direction the light travels. 45 puts the sun behind and to the left of the start; 195 puts it ahead and a little to the right
		float SunLux;
		FLinearColor SunColor;
		float ExposureEv;
		float MieScale;
		FLinearColor MieColor;
		float MieAnisotropy;  // Near 1 the dust throws its light forward, which makes a glow around the sun
		float RayleighScale;
		float SkyLightIntensity;
		FLinearColor FogColor;
		float FogDensity;
	};
	FLook Look{20.0, 45.0, 10.0f, FLinearColor(1.0f, 0.96f, 0.90f), 0.0f, 0.02f, FLinearColor(0.95f, 0.60f, 0.32f), 0.5f, 0.0005f, 1.0f, FLinearColor(0.42f, 0.50f, 0.64f), 0.004f};
	FString Preset = TEXT("default");
	FParse::Value(FCommandLine::Get(), TEXT("RoverLight="), Preset);
	bool bFixedExposure = true;
	if (Preset == TEXT("noon"))
	{
		// High sun, white-yellow light, a bright butterscotch sky, and a cool grey-blue haze
		Look = {58.0, 45.0, 4.3f, FLinearColor(1.0f, 0.97f, 0.90f), 10.8f, 0.02f, FLinearColor(0.95f, 0.60f, 0.32f), 0.5f, 0.0005f, 1.0f, FLinearColor(0.42f, 0.50f, 0.64f), 0.004f};
	}
	else if (Preset == TEXT("afternoon"))
	{
		// Lower, amber light, a deeper orange sky, long shadows, and a warm violet-grey haze
		Look = {22.0, 45.0, 4.3f, FLinearColor(1.0f, 0.80f, 0.56f), 10.8f, 0.035f, FLinearColor(0.95f, 0.50f, 0.26f), 0.6f, 0.0005f, 0.8f, FLinearColor(0.56f, 0.46f, 0.52f), 0.005f};
	}
	else if (Preset == TEXT("sunset"))
	{
		// The sun is almost on the horizon, ahead of the rover and a little to its right, its light red. The dust scatters blue forward in a narrow cone, so
		// the sky around the sun glows blue, as in the photographs of Martian sunsets, and the haze turns blue-violet
		Look = {5.5, 195.0, 2.4f, FLinearColor(1.0f, 0.42f, 0.20f), 11.4f, 0.14f, FLinearColor(0.22f, 0.42f, 1.0f), 0.93f, 0.001f, 0.5f, FLinearColor(0.30f, 0.34f, 0.70f), 0.007f};
	}
	else
	{
		bFixedExposure = false; // The original look, with the engine's own exposure
	}
	if (FParse::Value(FCommandLine::Get(), TEXT("RoverExposure="), Look.ExposureEv))
	{
		bFixedExposure = true; // -RoverExposure=EV overrides the preset's value, for tuning
	}
	// Movable, since nothing is baked.
	const FTransform SunTransform(FRotator(-Look.SunElevationDeg, Look.SunYawDeg, 0.0));
	ADirectionalLight* Sun = World->SpawnActorDeferred<ADirectionalLight>(ADirectionalLight::StaticClass(), SunTransform, nullptr,
		nullptr, ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
	// ADirectionalLight::GetComponent is editor-only; ALight::GetLightComponent exists in every build.
	Sun->GetLightComponent()->SetMobility(EComponentMobility::Movable);
	Sun->FinishSpawning(SunTransform);
	if (UDirectionalLightComponent* SunLight = Cast<UDirectionalLightComponent>(Sun->GetLightComponent()))
	{
		SunLight->SetAtmosphereSunLight(true);
		SunLight->SetLightColor(Look.SunColor);
		if (Preset != TEXT("default"))
		{
			SunLight->SetIntensity(Look.SunLux);
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
		Exposure->Settings.AutoExposureBias = Look.ExposureEv;
		UE_LOG(LogRoverloom, Display, TEXT("Rover light preset '%s': sun %.1f deg above the horizon, %.1f lux, fixed exposure %.1f"), *Preset, Look.SunElevationDeg, Look.SunLux, Look.ExposureEv);
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
		Air->SetRayleighScatteringScale(Look.RayleighScale);
		Air->SetRayleighExponentialDistribution(11.0f); // km, Mars's scale height
		Air->SetMieScatteringScale(Look.MieScale);
		Air->SetMieScattering(Look.MieColor);
		Air->SetMieAbsorptionScale(0.006f);
		Air->SetMieAbsorption(FLinearColor(0.35f, 0.55f, 0.75f));
		Air->SetMieAnisotropy(Look.MieAnisotropy);
		Air->SetMieExponentialDistribution(11.0f);
	}

	ASkyLight* Sky = World->SpawnActorDeferred<ASkyLight>(ASkyLight::StaticClass(), FTransform::Identity, nullptr, nullptr,
		ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
	Sky->GetLightComponent()->SetMobility(EComponentMobility::Movable);
	Sky->GetLightComponent()->SetRealTimeCapture(true);
	if (Preset != TEXT("default"))
	{
		Sky->GetLightComponent()->SetIntensity(Look.SkyLightIntensity);
	}
	Sky->FinishSpawning(FTransform::Identity);

	AExponentialHeightFog* Fog = World->SpawnActor<AExponentialHeightFog>(AExponentialHeightFog::StaticClass(), FTransform::Identity, SpawnParams);
	if (UExponentialHeightFogComponent* FogComponent = Fog ? Fog->FindComponentByClass<UExponentialHeightFogComponent>() : nullptr)
	{
		if (bHasLandscape)
		{
			// Distance haze for the Gale level: nothing within 400 m, then a color that thickens with distance, so the ridges of the
			// horizon Landscape recede. Its color follows the preset. The owner asked for a bluish haze by day; Mars's own daytime
			// dust haze is butterscotch, and its blue is a glow near the sun at sunset, so these are chosen looks, not measurements.
			FogComponent->SetFogInscatteringColor(Look.FogColor);
			FogComponent->SetFogDensity(Look.FogDensity);
			FogComponent->SetFogHeightFalloff(0.25f);
			FogComponent->SetStartDistance(40000.0f);
			float FogMax = Preset == TEXT("sunset") ? 0.55f : 0.92f; // Fog covers the sky too, at its maximum opacity; -RoverFogMax=F tunes it
			FParse::Value(FCommandLine::Get(), TEXT("RoverFogMax="), FogMax);
			FogComponent->SetFogMaxOpacity(FogMax);
		}
		else
		{
			FogComponent->SetFogInscatteringColor(FLinearColor(0.55f, 0.38f, 0.25f)); // Dust haze toward the horizon
			FogComponent->SetFogDensity(0.01f); // Half the default, so the horizon and shadows stay readable
		}
	}
	LightsSpawned = 4; // Sun, sky atmosphere, sky light, fog
}
