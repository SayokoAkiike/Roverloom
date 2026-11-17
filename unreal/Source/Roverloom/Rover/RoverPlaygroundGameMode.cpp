#include "RoverPlaygroundGameMode.h"
#include "DrawDebugHelpers.h"

#include "Components/DirectionalLightComponent.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Engine/CollisionProfile.h"
#include "NiagaraSystem.h"
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
#include "RoverEffects.h"
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
	if (FParse::Param(FCommandLine::Get(), TEXT("RoverNiagaraProbe")))
	{
		// What can be set from code on the template Niagara systems? Listed to the log, then the game goes on.
		static const TCHAR* Templates[] = {TEXT("FountainLightweight"), TEXT("DirectionalBurstLightweight"), TEXT("MinimalLightweight"),
			TEXT("SimpleExplosion"), TEXT("RadialBurst"), TEXT("DirectionalBurst")};
		for (const TCHAR* Name : Templates)
		{
			const FString Path = FString::Printf(TEXT("/Niagara/DefaultAssets/Templates/Systems/%s.%s"), Name, Name);
			UNiagaraSystem* System = LoadObject<UNiagaraSystem>(nullptr, *Path, nullptr, LOAD_NoWarn | LOAD_Quiet);
			if (!System)
			{
				UE_LOG(LogRoverloom, Display, TEXT("Niagara probe: %s not found"), *Path);
				continue;
			}
			TArray<FNiagaraVariable> Variables;
			System->GetExposedParameters().GetParameters(Variables);
			FString Names;
			for (const FNiagaraVariable& Variable : Variables)
			{
				Names += FString::Printf(TEXT(" [%s : %s]"), *Variable.GetName().ToString(), *Variable.GetType().GetName());
			}
			FString Emitters;
			for (const FNiagaraEmitterHandle& Handle : System->GetEmitterHandles())
			{
				Emitters += FString::Printf(TEXT(" %s"), *Handle.GetName().ToString());
			}
			UE_LOG(LogRoverloom, Display, TEXT("Niagara probe: %s has %d exposed parameters:%s; emitters:%s"), Name, Variables.Num(), *Names, *Emitters);
		}
	}
	AWorldSettings* Settings = GetWorld()->GetWorldSettings();
	Settings->bGlobalGravitySet = true;
	Settings->GlobalGravityZ = -MarsGravityCmps2;
	BindLandscape();
	ApplyProfile();
	SpawnTerrain();
	SpawnLights();
	SpawnRover();
	SpawnScatter();
	if (FParse::Param(FCommandLine::Get(), TEXT("RoverTutorial")))
	{
		// Visual guide for g3_reach_target only. Python remains the sole arrival judge.
		const FVector Target = RoverloomFrames::SiteToUnrealPosition(FVector(8.0, 0.0, 0.0));
		DrawDebugSphere(GetWorld(), Target, 200.0f, 32, FColor::Green, true, -1.0f, 0, 3.0f);
	}
	// Wheel ruts and dust, as looks only (see RoverEffects.h). -RoverDust=0 and -RoverRuts=0 turn them off.
	int32 DustOn = 1;
	int32 RutsOn = 1;
	FParse::Value(FCommandLine::Get(), TEXT("RoverDust="), DustOn);
	FParse::Value(FCommandLine::Get(), TEXT("RoverRuts="), RutsOn);
	if (Rover && bHasLandscape && (DustOn != 0 || RutsOn != 0))
	{
		Effects = GetWorld()->SpawnActor<ARoverEffects>();
		if (!Effects->Init(Rover, DustOn != 0, RutsOn != 0))
		{
			Effects->Destroy();
			Effects = nullptr;
		}
	}
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
	int32 FarOn = 1; // -RoverFar=0 hides the far Landscape (Mount Sharp and the crater rim), for before-and-after shots
	FParse::Value(FCommandLine::Get(), TEXT("RoverFar="), FarOn);
	for (TActorIterator<ALandscapeProxy> It(GetWorld()); It; ++It)
	{
		if (FarOn == 0 && It->GetActorLabel() == TEXT("GaleFar"))
		{
			It->SetActorHiddenInGame(true);
			continue;
		}
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
	double StartYawDeg = 0.0; // -RoverStartYawDeg=D turns the rover at the start, for looking at the sun. Only for viewing
	FParse::Value(FCommandLine::Get(), TEXT("RoverStartYawDeg="), StartYawDeg);
	Rover = GetWorld()->SpawnActor<ARoverPawn>(ARoverPawn::StaticClass(), FVector(StartCm.X, StartCm.Y, GroundCm + RoverloomRover::RideHeightCm),
		FRotator(0.0, StartYawDeg, 0.0), SpawnParams);
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
		FLinearColor SunGlow; // Fog light toward the sun: the glow of the dust around it. Black for none
		float SunGlowExponent; // Larger is a tighter glow
	};
	FLook Look{20.0, 45.0, 10.0f, FLinearColor(1.0f, 0.96f, 0.90f), 0.0f, 0.02f, FLinearColor(0.95f, 0.60f, 0.32f), 0.5f, 0.0005f, 1.0f, FLinearColor(0.42f, 0.50f, 0.64f), 0.004f, FLinearColor::Black, 8.0f};
	FString Preset = TEXT("default");
	FParse::Value(FCommandLine::Get(), TEXT("RoverLight="), Preset);
	bool bFixedExposure = true;
	bool bBlueSky = false;
	if (Preset == TEXT("noon"))
	{
		// High sun, white-yellow light, a bright butterscotch sky, and a cool grey-blue haze
		Look = {58.0, 45.0, 4.3f, FLinearColor(1.0f, 0.97f, 0.90f), 10.8f, 0.02f, FLinearColor(0.95f, 0.60f, 0.32f), 0.5f, 0.0005f, 1.0f, FLinearColor(0.30f, 0.40f, 0.62f), 0.007f, FLinearColor::Black, 8.0f};
	}
	else if (Preset == TEXT("afternoon"))
	{
		// Lower, amber light, a deeper orange sky, long shadows, and a warm violet-grey haze
		Look = {22.0, 45.0, 4.3f, FLinearColor(1.0f, 0.80f, 0.56f), 10.8f, 0.035f, FLinearColor(0.95f, 0.50f, 0.26f), 0.6f, 0.0005f, 0.8f, FLinearColor(0.56f, 0.46f, 0.52f), 0.005f, FLinearColor::Black, 8.0f};
	}
	else if (Preset == TEXT("sunset"))
	{
		// The sun is almost on the horizon, ahead of the rover and a little to its right, its light red. The dust scatters blue forward in a narrow cone, so
		// the sky around the sun glows blue, as in the photographs of Martian sunsets, and the haze turns blue-violet
		Look = {5.5, 195.0, 2.4f, FLinearColor(1.0f, 0.42f, 0.20f), 11.4f, 0.14f, FLinearColor(0.22f, 0.42f, 1.0f), 0.93f, 0.001f, 0.5f, FLinearColor(0.48f, 0.22f, 0.14f), 0.007f, FLinearColor::Black, 5.0f}; // The sun-side fog glow (0.30, 0.52, 1.6) had no visible effect on the sky, even at 12 times (tested 2026-11-16)
	}
	else if (Preset == TEXT("sunset_blue"))
	{
		// The same low sun, but a pale sun light and a layer that absorbs red and green along the long path: the sky around the sun turns
		// blue-white, fading to violet and pink at the horizon, as in the blue sunsets photographed on Mars. The ground is lit by that
		// sky, so it is dim and its exposure is raised. Found by trial: docs/results/sky-sunset/README.md
		Look = {5.5, 195.0, 2.4f, FLinearColor(1.0f, 0.9f, 0.8f), 12.2f, 0.14f, FLinearColor(0.22f, 0.42f, 1.0f), 0.93f, 0.001f, 0.5f, FLinearColor(0.36f, 0.34f, 0.60f), 0.007f, FLinearColor::Black, 5.0f};
		bBlueSky = true;
	}
	else
	{
		bFixedExposure = false; // The original look, with the engine's own exposure
	}
	// Sky tuning overrides, for finding a look from the command line without a rebuild: the sun, and the atmosphere's own scattering
	// (Rayleigh and Mie colour, scale, absorption). Colours are r,g,b.
	auto Number = [](const TCHAR* Key, double& Value) { FParse::Value(FCommandLine::Get(), Key, Value); };
	auto ColorOf = [](const TCHAR* Key, FLinearColor& Color)
	{
		FString Text;
		if (FParse::Value(FCommandLine::Get(), Key, Text, false))
		{
			TArray<FString> Parts;
			Text.ParseIntoArray(Parts, TEXT(","));
			if (Parts.Num() >= 3)
			{
				Color = FLinearColor(FCString::Atof(*Parts[0]), FCString::Atof(*Parts[1]), FCString::Atof(*Parts[2]));
			}
		}
	};
	Number(TEXT("RoverSunElevation="), Look.SunElevationDeg);
	Number(TEXT("RoverSunYaw="), Look.SunYawDeg);
	double MieScaleD = Look.MieScale, MieAnisoD = Look.MieAnisotropy, RayleighScaleD = Look.RayleighScale;
	double MieAbsorptionScale = 0.006, RayleighPowerD = 1.0;
	FLinearColor RayleighColor(0.005802f, 0.013558f, 0.0331f);
	FLinearColor MieAbsorption(0.35f, 0.55f, 0.75f);
	FLinearColor OtherAbsorption(0.000650f, 0.001881f, 0.000085f); // The engine default, an ozone-like layer
	double OtherAbsorptionScale = 1.0;
	if (bBlueSky)
	{
		OtherAbsorption = FLinearColor(1.0f, 0.55f, 0.05f); // Absorbs red and green, leaves blue
		OtherAbsorptionScale = 0.07;
	}
	Number(TEXT("RoverMieScale="), MieScaleD);
	Number(TEXT("RoverMieAniso="), MieAnisoD);
	Number(TEXT("RoverRayleighScale="), RayleighScaleD);
	Number(TEXT("RoverMieAbsScale="), MieAbsorptionScale);
	ColorOf(TEXT("RoverSunColor="), Look.SunColor);
	ColorOf(TEXT("RoverOtherAbsColor="), OtherAbsorption);
	Number(TEXT("RoverOtherAbsScale="), OtherAbsorptionScale);
	ColorOf(TEXT("RoverMieColor="), Look.MieColor);
	ColorOf(TEXT("RoverRayleighColor="), RayleighColor);
	ColorOf(TEXT("RoverMieAbsColor="), MieAbsorption);
	Look.MieScale = static_cast<float>(MieScaleD);
	Look.MieAnisotropy = static_cast<float>(MieAnisoD);
	Look.RayleighScale = static_cast<float>(RayleighScaleD);
	(void)RayleighPowerD;
	double GlowScale = 1.0; // -RoverGlowScale=F scales the sun-side fog glow, for tuning
	FParse::Value(FCommandLine::Get(), TEXT("RoverGlowScale="), GlowScale);
	Look.SunGlow = Look.SunGlow * static_cast<float>(GlowScale);
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

	FString Profile;
	FParse::Value(FCommandLine::Get(), TEXT("RoverProfile="), Profile);
	if (Profile == TEXT("capture"))
	{
		// A grade like a rover's photographs: muted colour, firmer contrast, a little grain and vignette. Capture only, so that Dev
		// shows the scene as it is. Tuned by eye; these are not calibrated to any camera.
		APostProcessVolume* Grade = World->SpawnActor<APostProcessVolume>(APostProcessVolume::StaticClass(), FTransform::Identity, SpawnParams);
		Grade->bUnbound = true;
		Grade->Priority = 10.0f;
		FPostProcessSettings& G = Grade->Settings;
		G.bOverride_ColorSaturation = true;
		G.ColorSaturation = FVector4(0.86, 0.86, 0.86, 1.0);
		G.bOverride_ColorContrast = true;
		G.ColorContrast = FVector4(1.12, 1.12, 1.12, 1.0);
		G.bOverride_FilmGrainIntensity = true;
		G.FilmGrainIntensity = 0.22f;
		G.bOverride_VignetteIntensity = true;
		G.VignetteIntensity = 0.35f;
		UE_LOG(LogRoverloom, Display, TEXT("Rover capture grade: saturation 0.86, contrast 1.12, film grain 0.22, vignette 0.35"));
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
		Air->SetRayleighScattering(RayleighColor);
		Air->SetRayleighScatteringScale(Look.RayleighScale);
		Air->SetRayleighExponentialDistribution(11.0f); // km, Mars's scale height
		Air->SetMieScatteringScale(Look.MieScale);
		Air->SetMieScattering(Look.MieColor);
		Air->SetMieAbsorptionScale(static_cast<float>(MieAbsorptionScale));
		Air->SetMieAbsorption(MieAbsorption);
		Air->SetOtherAbsorption(OtherAbsorption);
		Air->SetOtherAbsorptionScale(static_cast<float>(OtherAbsorptionScale));
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
			// -RoverFogColor=r,g,b, -RoverFogDensity=F, and -RoverFogFalloff=F tune the haze from the command line
			FLinearColor HazeColor = Look.FogColor;
			double HazeDensity = Look.FogDensity;
			double HazeFalloff = 0.12; // The haze thins slowly with height, so a mountain 5 km high is fogged top to bottom
			FString HazeText;
			if (FParse::Value(FCommandLine::Get(), TEXT("RoverFogColor="), HazeText, false))
			{
				TArray<FString> Parts;
				HazeText.ParseIntoArray(Parts, TEXT(","));
				if (Parts.Num() >= 3)
				{
					HazeColor = FLinearColor(FCString::Atof(*Parts[0]), FCString::Atof(*Parts[1]), FCString::Atof(*Parts[2]));
				}
			}
			FParse::Value(FCommandLine::Get(), TEXT("RoverFogDensity="), HazeDensity);
			FParse::Value(FCommandLine::Get(), TEXT("RoverFogFalloff="), HazeFalloff);
			FogComponent->SetFogInscatteringColor(HazeColor);
			FogComponent->SetFogDensity(static_cast<float>(HazeDensity));
			FogComponent->SetFogHeightFalloff(static_cast<float>(HazeFalloff));
			FogComponent->SetStartDistance(40000.0f);
			float FogMax = Preset == TEXT("sunset") ? 0.55f : 0.92f; // Fog covers the sky too, at its maximum opacity; -RoverFogMax=F tunes it
			FParse::Value(FCommandLine::Get(), TEXT("RoverFogMax="), FogMax);
			FogComponent->SetFogMaxOpacity(FogMax);
			if (!Look.SunGlow.Equals(FLinearColor::Black))
			{
				// The fog covers the sky, so light added toward the sun makes a glow around it. At sunset it is blue, while the fog
				// itself is red-brown toward the horizon, as in the photographs of Martian sunsets
				FogComponent->SetDirectionalInscatteringColor(Look.SunGlow);
				FogComponent->SetDirectionalInscatteringExponent(Look.SunGlowExponent);
				FogComponent->SetDirectionalInscatteringStartDistance(100.0f);
			}
		}
		else
		{
			FogComponent->SetFogInscatteringColor(FLinearColor(0.55f, 0.38f, 0.25f)); // Dust haze toward the horizon
			FogComponent->SetFogDensity(0.01f); // Half the default, so the horizon and shadows stay readable
		}
	}
	LightsSpawned = 4; // Sun, sky atmosphere, sky light, fog
}
