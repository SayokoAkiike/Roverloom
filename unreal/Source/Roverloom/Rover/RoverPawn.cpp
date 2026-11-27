#include "RoverPawn.h"
#include "DrawDebugHelpers.h"

#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/StaticMeshComponent.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "Engine/CollisionProfile.h"
#include "Engine/LocalPlayer.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "IPAddress.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "SocketSubsystem.h"
#include "Sockets.h"
#include "InputAction.h"
#include "InputActionValue.h"
#include "InputCoreTypes.h"
#include "InputMappingContext.h"
#include "InputModifiers.h"
#include "DynamicRHI.h"
#include "RHIGlobals.h"
#include "HAL/PlatformTime.h"
#include "Misc/App.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformMisc.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "PhysicalMaterials/PhysicalMaterial.h"
#include "PhysicsEngine/PhysicsSettings.h"
#include "RenderTimer.h"
#include "UnrealClient.h"
#include "UObject/ConstructorHelpers.h"
#include "RaceOpponent.h"

#include "../Bridge/Frames.h"
#include "../Roverloom.h"
#include "../WheelSpike/WheelRig.h"
#include "Greybox.h"
#include "RoverDrive.h"

using namespace RoverloomCommand;
using namespace RoverloomRover;

const TCHAR* ARoverPawn::KeyboardSource = TEXT("keyboard");
const TCHAR* ARoverPawn::AgentSource = TEXT("agent");

namespace
{
	// Above this speed the rig has diverged, as WheelSpikeGameMode's "diverged" outcome.
	const double DivergedSpeedCmps = 1000.0;
	// Below this depth under the start the rover has fallen through the ground. Relative to the start, not to z = 0:
	// on real terrain the course can lie well below the site origin (Noctis Sprint starts 15 m under it).
	const double FallenBelowStartCm = 2000.0;
	const double FreeCameraSpeedCmps = 800.0;
	const double FreeCameraLiftCmps = 400.0;
	// V2 visual model: struts run inboard of the wheels, at scripts/blender/build_rover.py's ARM_Y (0.877 m).
	const double ModelArmYCm = 87.7;
	const TCHAR* const ModelBodyPath = TEXT("/Game/Rover/SM_RoverBody.SM_RoverBody");
	const TCHAR* const ModelWheelPath = TEXT("/Game/Rover/SM_RoverWheel.SM_RoverWheel");
	const TCHAR* const ModelStrutPath = TEXT("/Game/Rover/SM_RoverStrut.SM_RoverStrut");
	const TCHAR* const ModelAxlePath = TEXT("/Game/Rover/SM_RoverAxle.SM_RoverAxle");
	const double LookDegPerUnit = 0.15;

	void Tint(UStaticMeshComponent* Mesh, const FLinearColor& Color, float Roughness = 0.5f)
	{
		RoverloomGreybox::Paint(Mesh, Color, Roughness);
	}
}

ARoverPawn::ARoverPawn()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PrePhysics;
	// The pawn follows the rig's body. Controller rotation must never turn it.
	bUseControllerRotationPitch = false;
	bUseControllerRotationYaw = false;
	bUseControllerRotationRoll = false;
	AutoPossessPlayer = EAutoReceiveInput::Disabled;

	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeMesh(TEXT("/Engine/BasicShapes/Cube.Cube"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CylinderMesh(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));

	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	Root->SetMobility(EComponentMobility::Movable);
	RootComponent = Root;

	// Basic shapes are 100 cm across and centered; cylinders stand on Z.
	auto MakePart = [this](const TCHAR* Name, UStaticMesh* Mesh, const FVector& Location, const FRotator& Rotation, const FVector& Scale)
	{
		UStaticMeshComponent* Part = CreateDefaultSubobject<UStaticMeshComponent>(Name);
		Part->SetupAttachment(Root);
		Part->SetStaticMesh(Mesh);
		Part->SetRelativeLocationAndRotation(Location, Rotation);
		Part->SetRelativeScale3D(Scale);
		Part->SetCollisionProfileName(UCollisionProfile::NoCollision_ProfileName);
		Part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Part->SetGenerateOverlapEvents(false);
		Part->SetCanEverAffectNavigation(false);
		return Part;
	};

	UStaticMesh* Cube = CubeMesh.Object;
	UStaticMesh* Cylinder = CylinderMesh.Object;
	const FVector2D WheelScale(2.0 * WheelRadiusCm / 100.0, 0.2); // 50 cm diameter, 20 cm wide
	for (int32 Index = 0; Index < NumWheels; ++Index)
	{
		const FVector Mount = WheelMountCm(Index);
		Wheels.Add(MakePart(*FString::Printf(TEXT("Wheel%d"), Index), Cylinder, Mount, FRotator(0.0, 0.0, 90.0),
			FVector(WheelScale.X, WheelScale.X, WheelScale.Y)));
		// A bar across each wheel, slightly wider than the tire, so that its spin can be seen.
		WheelMarks.Add(MakePart(*FString::Printf(TEXT("WheelMark%d"), Index), Cube, Mount, FRotator::ZeroRotator, FVector(0.42, 0.22, 0.06)));
		Legs.Add(MakePart(*FString::Printf(TEXT("Leg%d"), Index), Cube, Mount, FRotator::ZeroRotator, FVector(0.06, 0.06, 0.25)));
	}
	const double RockerLengthCm = 2.0 * MountXCm + 20.0;
	for (const double Y : {-HalfTrackCm, HalfTrackCm})
	{
		Parts.Add(MakePart(Y < 0.0 ? TEXT("RockerLeft") : TEXT("RockerRight"), Cube, FVector(0.0, Y, MountZCm), FRotator::ZeroRotator,
			FVector(RockerLengthCm / 100.0, 0.08, 0.08)));
	}
	// The mast reaches 2.0 m above flat ground, where its camera sits: body center 70 cm, plus 130 cm.
	const FVector MastBase(85.0, 0.0, BodySizeCm.Z / 2.0);
	const double MastTopZ = 130.0;
	Parts.Add(MakePart(TEXT("Mast"), Cylinder, FVector(MastBase.X, 0.0, (MastBase.Z + MastTopZ) / 2.0), FRotator::ZeroRotator,
		FVector(0.08, 0.08, (MastTopZ - MastBase.Z) / 100.0)));
	Parts.Add(MakePart(TEXT("MastHead"), Cube, FVector(MastBase.X, 0.0, MastTopZ + 4.0), FRotator::ZeroRotator, FVector(0.16, 0.36, 0.12)));
	Parts.Add(MakePart(TEXT("Panel"), Cube, FVector(-45.0, 0.0, BodySizeCm.Z / 2.0 + 12.0), FRotator::ZeroRotator, FVector(2.2, 1.8, 0.03)));
	// Original procedural panel cells and hubs, with no project art or collision changes.
	for (int32 X = 0; X < 8; ++X)
	{
		Parts.Add(MakePart(*FString::Printf(TEXT("PanelCell%d"), X), Cube,
			FVector(-135.0 + X * 25.0, 0.0, BodySizeCm.Z / 2.0 + 14.0), FRotator::ZeroRotator, FVector(0.012, 1.7, 0.012)));
	}
	for (int32 I = 0; I < NumWheels; ++I)
	{
		const FVector Mount = WheelMountCm(I);
		Parts.Add(MakePart(*FString::Printf(TEXT("Hub%d"), I), Cylinder,
			Mount + FVector(0.0, Mount.Y < 0 ? -12.0 : 12.0, 0.0), FRotator(0.0, 0.0, 90.0), FVector(0.14, 0.14, 0.04)));
	}
	// V2 slots stay empty and hidden unless ApplyModelV2 finds the meshes at BeginPlay.
	ModelBody = MakePart(TEXT("ModelBody"), nullptr, FVector::ZeroVector, FRotator::ZeroRotator, FVector::OneVector);
	ModelBody->SetVisibility(false);
	for (int32 Index = 0; Index < NumWheels; ++Index)
	{
		UStaticMeshComponent* Axle = MakePart(*FString::Printf(TEXT("ModelAxle%d"), Index), nullptr, WheelMountCm(Index),
			FRotator::ZeroRotator, FVector::OneVector);
		Axle->SetVisibility(false);
		ModelAxles.Add(Axle);
	}

	ChaseArm = CreateDefaultSubobject<USpringArmComponent>(TEXT("ChaseArm"));
	ChaseArm->SetupAttachment(Root);
	ChaseArm->SetRelativeLocationAndRotation(FVector(0.0, 0.0, 40.0), FRotator(-15.0, 0.0, 0.0));
	ChaseArm->TargetArmLength = 900.0f;
	ChaseArm->bDoCollisionTest = false; // No traces: the camera never queries or touches the world
	ChaseArm->bEnableCameraLag = true;
	ChaseArm->CameraLagSpeed = 5.0f;
	ChaseArm->bEnableCameraRotationLag = true;
	ChaseArm->CameraRotationLagSpeed = 4.0f;
	ChaseArm->bInheritPitch = false;
	ChaseArm->bInheritRoll = false;
	ChaseArm->bInheritYaw = true;

	ChaseCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("ChaseCamera"));
	ChaseCamera->SetupAttachment(ChaseArm, USpringArmComponent::SocketName);
	ChaseCamera->SetFieldOfView(70.0f);

	// Mast: 2.0 m, pitched 5 degrees down, 45 degree horizontal field of view, as shot 1 in site-and-look-references.md.
	MastCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("MastCamera"));
	MastCamera->SetupAttachment(Root);
	MastCamera->SetRelativeLocationAndRotation(FVector(MastBase.X + 10.0, 0.0, MastTopZ), FRotator(-5.0, 0.0, 0.0));
	MastCamera->SetFieldOfView(45.0f);
	MastCamera->SetAutoActivate(false);

	// Front hazard camera: low and wide, looking at the ground ahead of the front wheels.
	HazardCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("HazardCamera"));
	HazardCamera->SetupAttachment(Root);
	HazardCamera->SetRelativeLocationAndRotation(FVector(BodySizeCm.X / 2.0 + 5.0, 0.0, -10.0), FRotator(-25.0, 0.0, 0.0));
	HazardCamera->SetFieldOfView(110.0f);
	HazardCamera->SetAutoActivate(false);

	Router = MakeUnique<FCommandRouter>(TArray<FString>{KeyboardSource, AgentSource}, KeyboardSource, MaxSpeedMps, MaxYawRateRadps);
	WheelAnglesRad.Init(0.0, NumWheels);
}

const TCHAR* ARoverPawn::CameraName(ERoverCamera InCamera)
{
	switch (InCamera)
	{
	case ERoverCamera::Chase:
		return TEXT("Chase");
	case ERoverCamera::Mast:
		return TEXT("Mast, 2.0 m");
	case ERoverCamera::Hazard:
		return TEXT("Front hazard");
	case ERoverCamera::Free:
		return TEXT("Free");
	}
	return TEXT("?");
}

void ARoverPawn::BeginPlay()
{
	Super::BeginPlay();
	bRally = FParse::Param(FCommandLine::Get(), TEXT("RoverRally"));
	Status.bRace = FParse::Param(FCommandLine::Get(), TEXT("RoverRace"));
	StartTransform = FTransform(GetActorQuat(), GetActorLocation());
	FParse::Value(FCommandLine::Get(), TEXT("RoverShotDir="), ShotDir);
	FParse::Value(FCommandLine::Get(), TEXT("RoverRaceDiagnose="), RaceDiagnoseDir);
	FParse::Value(FCommandLine::Get(), TEXT("RoverBench="), BenchSeconds);
	FString DrivePreset;
	if (FParse::Value(FCommandLine::Get(), TEXT("RoverDrive="), DrivePreset))
	{
		// f1-flat: straight, spin, and arc on the flat ground at the start, with stops between, at the command limits.
		if (DrivePreset == TEXT("f1-flat"))
		{
			DrivePhases = {
				{TEXT("settle"), 3.0, 0.0, 0.0},
				{TEXT("straight"), 8.0, MaxSpeedMps, 0.0},
				{TEXT("stop-after-straight"), 4.0, 0.0, 0.0},
				{TEXT("spin-left"), 8.0, 0.0, MaxYawRateRadps},
				{TEXT("stop-after-spin"), 4.0, 0.0, 0.0},
				{TEXT("arc-left"), 8.0, 0.5 * MaxSpeedMps, 0.5 * MaxYawRateRadps},
				{TEXT("stop-after-arc"), 4.0, 0.0, 0.0},
			};
		}
		// f1-step: straight ahead into the 25 cm outcrop step 12 m from the start (x 12-18 m).
		else if (DrivePreset == TEXT("f1-step"))
		{
			DrivePhases = {
				{TEXT("settle"), 3.0, 0.0, 0.0},
				{TEXT("approach"), 18.0, MaxSpeedMps, 0.0},
				{TEXT("step"), 16.0, MaxSpeedMps, 0.0},
				{TEXT("stop"), 4.0, 0.0, 0.0},
			};
		}
		// f1-ramp15: turn left a quarter, cross to the 15-degree ramp's lane (15 m left), turn back, and climb it
		// (ramp from x 6 m, 12 m long). Turn times assume F2's 98% yaw tracking.
		else if (DrivePreset == TEXT("f1-ramp15"))
		{
			const double Quarter = 0.5 * PI / (0.98 * MaxYawRateRadps);
			DrivePhases = {
				{TEXT("settle"), 3.0, 0.0, 0.0},
				{TEXT("turn-left"), Quarter, 0.0, MaxYawRateRadps},
				{TEXT("cross"), 30.0, MaxSpeedMps, 0.0},
				{TEXT("turn-right"), Quarter, 0.0, -MaxYawRateRadps},
				{TEXT("approach"), 10.0, MaxSpeedMps, 0.0},
				{TEXT("climb"), 26.0, MaxSpeedMps, 0.0},
				{TEXT("stop-on-slope"), 6.0, 0.0, 0.0},
			};
		}
		// g3-reach: drive 10 m straight ahead and stop, with the mission link open; the Mission Core judges the target.
		else if (DrivePreset == TEXT("g3-reach"))
		{
			DrivePhases = {
				{TEXT("settle"), 6.0, 0.0, 0.0},
				{TEXT("drive-to-target"), 20.0, MaxSpeedMps, 0.0},
				{TEXT("stop"), 10.0, 0.0, 0.0},
			};
			MissionLinkStart();
		}
		// G4a: play-g3 opens the mission link for a person at the keyboard; keys-g3 does the same and simulates holding W.
		else if (DrivePreset == TEXT("play-g3") || DrivePreset == TEXT("keys-g3"))
		{
			MissionLinkStart();
			if (DrivePreset == TEXT("keys-g3"))
			{
				KeySimStartS = 6.0;
				KeySimSeconds = 20.0;
			}
		}
		UE_LOG(LogRoverloom, Display, TEXT("Rover drive script '%s': %d phases"), *DrivePreset, DrivePhases.Num());
	}
	for (UStaticMeshComponent* Wheel : Wheels)
	{
		Tint(Wheel, FLinearColor(0.05f, 0.05f, 0.05f));
	}
	for (UStaticMeshComponent* Mark : WheelMarks)
	{
		Tint(Mark, FLinearColor(0.8f, 0.8f, 0.75f));
	}
	for (UStaticMeshComponent* Leg : Legs)
	{
		Tint(Leg, FLinearColor(0.5f, 0.5f, 0.52f));
	}
	for (UStaticMeshComponent* Part : Parts)
	{
		Tint(Part, Part->GetName() == TEXT("Panel") ? FLinearColor(0.03f, 0.05f, 0.12f) : FLinearColor(0.6f, 0.6f, 0.62f));
	}
	// -RoverModel=greybox keeps the basic shapes, for before-and-after shots under the same conditions.
	FString Model;
	FParse::Value(FCommandLine::Get(), TEXT("RoverModel="), Model);
	if (Model != TEXT("greybox"))
	{
		ApplyModelV2();
	}
	SpawnRig();
}

bool ARoverPawn::ApplyModelV2()
{
	// Visual meshes only: every component here has collision disabled, so physics never sees them.
	auto Load = [](const TCHAR* Path) { return LoadObject<UStaticMesh>(nullptr, Path, nullptr, LOAD_NoWarn | LOAD_Quiet); };
	UStaticMesh* BodyMesh = Load(ModelBodyPath);
	UStaticMesh* WheelMesh = Load(ModelWheelPath);
	UStaticMesh* StrutMesh = Load(ModelStrutPath);
	UStaticMesh* AxleMesh = Load(ModelAxlePath);
	if (!BodyMesh || !WheelMesh || !StrutMesh || !AxleMesh)
	{
		UE_LOG(LogRoverloom, Display, TEXT("Rover model: greybox (V2 meshes not found under /Game/Rover)"));
		return false;
	}
	// Import checks, logged for the record: the body's front (sample arm) reaches +113.5 cm and its rear (solar deck)
	// -175 cm; the wheel's radius is 25 cm. A mirrored or rotated import shows here.
	const FBox BodyBox = BodyMesh->GetBoundingBox();
	const FBox WheelBox = WheelMesh->GetBoundingBox();
	const FBox AxleBox = AxleMesh->GetBoundingBox();
	UE_LOG(LogRoverloom, Display, TEXT("Rover model: V2. Body X %.1f..%.1f cm (expect -175.0..113.5), Z %.1f..%.1f; wheel X %.1f..%.1f, Z %.1f..%.1f (expect +-25.0)"),
		BodyBox.Min.X, BodyBox.Max.X, BodyBox.Min.Z, BodyBox.Max.Z, WheelBox.Min.X, WheelBox.Max.X, WheelBox.Min.Z, WheelBox.Max.Z);
	if (FMath::Abs(BodyBox.Max.X - 113.5) > 2.0 || FMath::Abs(BodyBox.Min.X + 175.0) > 2.0 || FMath::Abs(WheelBox.Max.Z - WheelRadiusCm) > 1.0)
	{
		UE_LOG(LogRoverloom, Warning, TEXT("Rover model: V2 bounds differ from the generator's; check the import's axes and units"));
	}
	bModelV2 = true;
	for (UStaticMeshComponent* Part : Parts)
	{
		Part->SetVisibility(false);
	}
	for (UStaticMeshComponent* Mark : WheelMarks)
	{
		Mark->SetVisibility(false);
	}
	ModelBody->SetStaticMesh(BodyMesh);
	ModelBody->SetVisibility(true);
	for (UStaticMeshComponent* Wheel : Wheels)
	{
		Wheel->SetStaticMesh(WheelMesh);
		Wheel->SetRelativeScale3D(FVector::OneVector);
		Wheel->SetMaterial(0, nullptr);
	}
	for (UStaticMeshComponent* Leg : Legs)
	{
		Leg->SetStaticMesh(StrutMesh);
		Leg->SetMaterial(0, nullptr);
	}
	// The axle runs from the wheel's center toward the body. Read which way the imported mesh points, and mirror it per side.
	const bool bAxlePointsPlusY = AxleBox.Max.Y > -AxleBox.Min.Y;
	for (int32 Index = 0; Index < ModelAxles.Num(); ++Index)
	{
		const bool bNeedsPlusY = WheelMountCm(Index).Y < 0.0;
		ModelAxles[Index]->SetStaticMesh(AxleMesh);
		ModelAxles[Index]->SetRelativeScale3D(FVector(1.0, bNeedsPlusY == bAxlePointsPlusY ? 1.0 : -1.0, 1.0));
		ModelAxles[Index]->SetVisibility(true);
	}
	return true;
}

void ARoverPawn::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	MissionLinkStop();
	if (Rig)
	{
		Rig->Destroy();
		Rig = nullptr;
	}
	if (FreeCamera)
	{
		FreeCamera->Destroy();
		FreeCamera = nullptr;
	}
	Super::EndPlay(EndPlayReason);
}

void ARoverPawn::SpawnRig()
{
	if (!RigMaterial)
	{
		// The model reads friction from its own parameter. This material matters only if the body touches the ground.
		RigMaterial = NewObject<UPhysicalMaterial>(this);
		RigMaterial->Friction = Friction;
		RigMaterial->StaticFriction = Friction;
		RigMaterial->Restitution = 0.0f;
		if (Status.bRace)
		{
			RigMaterial->Restitution = RoverloomRover::RaceRestitution; // rovers spring back when they meet
		}
	}
	FActorSpawnParameters SpawnParams;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	Rig = GetWorld()->SpawnActor<AWheelRig>(AWheelRig::StaticClass(), StartTransform.GetLocation(), StartTransform.Rotator(), SpawnParams);
	TArray<AWheelRig::FWheelSetup> Setups;
	for (int32 Index = 0; Index < NumWheels; ++Index)
	{
		Setups.Add({WheelMountCm(Index), Index < 3});
	}
	// Phase C's six-wheel rig: free rotation, sphere sweeps, 853.5 kg, friction 0.6. Solver options stay at defaults.
	Rig->Build(BodySizeCm, MassKg, Setups, false, false, true, Friction, RigMaterial);
	// In a race, physical rivals share the ground: wheels stand on static objects only, never on another rover.
	Rig->SetWheelsHitOnlyStatic(Status.bRace);
	FLinearColor Paint(0.75f, 0.72f, 0.66f);
	FString PaintText;
	if (FParse::Value(FCommandLine::Get(), TEXT("RoverPaint="), PaintText, false))
	{
		TArray<FString> Channels;
		PaintText.ParseIntoArray(Channels, TEXT(","));
		if (Channels.Num() == 3)
		{
			Paint = FLinearColor(FMath::Clamp(FCString::Atof(*Channels[0]), 0.0f, 1.0f), FMath::Clamp(FCString::Atof(*Channels[1]), 0.0f, 1.0f), FMath::Clamp(FCString::Atof(*Channels[2]), 0.0f, 1.0f));
		}
	}
	Tint(Rig->GetBody(), Paint, 0.7f);
	if (bModelV2)
	{
		// The V2 body mesh replaces the rig's box on screen. Hiding it changes rendering only, not collision or physics.
		Rig->GetBody()->SetVisibility(false);
	}
	bRigReady = false;
	WheelAnglesRad.Init(0.0, NumWheels);
}

void ARoverPawn::ResetRig(const FString& Reason)
{
	UE_LOG(LogRoverloom, Warning, TEXT("Rover rig reset: %s"), *Reason);
	if (Rig)
	{
		Rig->Destroy();
		Rig = nullptr;
	}
	++Status.Resets;
	Status.LastReset = Reason;
	SetActorTransform(StartTransform);
	SpawnRig();
}

void ARoverPawn::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	RecordFrame(DeltaSeconds);
	if (!Rig)
	{
		return;
	}
	if (!bRigReady)
	{
		// The body exists only after registration, and simulates from the frame IsReady first returns true.
		bRigReady = Rig->IsReady();
		Status.bReady = bRigReady;
		if (bRigReady)
		{
			ReadyTimeS = GetWorld()->GetTimeSeconds();
			if (MissionClockStartS < 0.0) MissionClockStartS = ReadyTimeS;
			bLoggedSettle = false;
			UE_LOG(LogRoverloom, Display, TEXT("Rover rig ready at %.2f s: %d wheels, drive model P (provisional)"), ReadyTimeS, Rig->NumWheels());
			LogRenderSettings(TEXT("start"));
		}
		FollowBody();
		UpdateFreeCamera(DeltaSeconds);
		return;
	}

	const double NowS = GetWorld()->GetTimeSeconds();
	MissionLinkTick(NowS);
	if (KeySimStartS >= 0.0)
	{
		const double Since = NowS - ReadyTimeS;
		const bool bHold = Since >= KeySimStartS && Since < KeySimStartS + KeySimSeconds;
		const APlayerController* PC = Cast<APlayerController>(GetController());
		const ULocalPlayer* LocalPlayer = PC ? PC->GetLocalPlayer() : nullptr;
		UEnhancedInputLocalPlayerSubsystem* Input = LocalPlayer ? LocalPlayer->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>() : nullptr;
		if (bHold && Input)
		{
			Input->InjectInputForAction(DriveAction, FInputActionValue(1.0f), {}, {}); // W, through the player's mapping
		}
		if (bHold != bKeySimLogged)
		{
			bKeySimLogged = bHold;
			UE_LOG(LogRoverloom, Display, TEXT("Rover simulated key W %s at %.2f s"), bHold ? TEXT("down") : TEXT("up"), Since);
		}
	}
	DriveScriptCommand(NowS);
	if (bKeyboardHeld)
	{
		FAction Requested;
		Requested.LinearVelocityMps = DriveInput * GearScale(Status.Gear) * MaxSpeedMps;
		Requested.YawRateRadps = TurnInput * MaxYawRateRadps;
		Router->SetActive(KeyboardSource); // A held key takes the rover back from an agent, starting from a stop
		Status.bClamped = Router->Submit(KeyboardSource, Requested, NowS).bClamped;
	}
	FAction Applied = Router->Current(NowS);
	if (bRally)
	{
		const double Scale = RallyStateReceivedS >= 0.0 && NowS - RallyStateReceivedS <= 2.0 ? RallyDriveScale : 0.0;
		Applied.LinearVelocityMps *= Scale;
		if (Scale <= 0.0) Applied.YawRateRadps = 0.0;
	}
	TArray<double> Targets;
	SkidSteerTargets(Applied, Targets, RoverloomRover::DriveTrackScale);
	Rig->SetTargets(Targets, Applied.IsStop() ? RoverloomWheel::EWheelMode::Brake : RoverloomWheel::EWheelMode::Drive);

	// Chaos clamps its step to MaxPhysicsDeltaTime; the wheel solve must use the same step, or a hitch would apply a
	// long step's impulses over a short one.
	const double MaxDt = UPhysicsSettings::Get()->MaxPhysicsDeltaTime;
	const double StepDt = FMath::Min(static_cast<double>(DeltaSeconds), MaxDt);
	Status.StepDtS = StepDt;
	Status.bStepClamped = StepDt < DeltaSeconds;
	Rig->StepWheels(StepDt);

	const UStaticMeshComponent* Body = Rig->GetBody();
	const FVector Location = Body->GetComponentLocation();
	const FVector Velocity = Body->GetPhysicsLinearVelocity();
	if (Location.ContainsNaN() || Velocity.ContainsNaN() || Velocity.Size() > DivergedSpeedCmps
		|| Location.Z < StartTransform.GetLocation().Z - FallenBelowStartCm)
	{
		FString Reason = TEXT("diverged");
		if (Location.ContainsNaN() || Velocity.ContainsNaN())
		{
			Reason = TEXT("nan");
		}
		else if (Velocity.Size() <= DivergedSpeedCmps)
		{
			Reason = FString::Printf(TEXT("fell to z %.0f cm, start z %.0f cm"), Location.Z, StartTransform.GetLocation().Z);
		}
		ResetRig(Reason);
		return;
	}

	FollowBody();
	UpdateWheels(StepDt);
	UpdateFreeCamera(DeltaSeconds);

	Status.Applied = Applied;
	Status.bWatchdogExpired = Router->WatchdogExpired(NowS);
	Status.bHasCommanded = Router->HasCommanded();
	Status.Source = Router->GetActive();
	Status.Camera = Camera;
	Status.ForwardMps = FVector::DotProduct(Velocity, Body->GetForwardVector()) / RoverloomFrames::UnrealCmPerM;
	Status.YawRateRadps = RoverloomFrames::UnrealToSiteAngularVelocity(Body->GetPhysicsAngularVelocityInRadians()).Z;
	Status.TiltDeg = FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(Body->GetUpVector().Z, -1.0, 1.0)));
	Status.SitePositionM = RoverloomFrames::UnrealToSitePosition(Location);
	Status.YawRad = -FMath::DegreesToRadians(Body->GetComponentRotation().Yaw); // Unreal's Y is the site's -Y
	Status.WheelsInContact = 0;
	for (const AWheelRig::FWheelRecord& Record : Rig->GetRecords())
	{
		Status.WheelsInContact += Record.Contact.bHit ? 1 : 0;
	}
	DriveScriptSample(NowS, StepDt);
	LogAndCapture(NowS);
	LogRaceDraw(NowS);
}

void ARoverPawn::LogRaceDraw(double NowS)
{
	if (RaceDiagnoseDir.IsEmpty() || !Status.bRace || MissionClockStartS < 0.0 || NowS - RaceDrawLastS < 0.2)
	{
		return;
	}
	RaceDrawLastS = NowS;
	const FVector You = Status.SitePositionM;
	FString Line = FString::Printf(TEXT("RaceDraw t=%.2f you=%.3f,%.3f,%.4f"), NowS - MissionClockStartS, You.X, You.Y, Status.YawRad);
	double Nearest = 1e9;
	for (const TPair<FString, TObjectPtr<ARaceOpponent>>& Pair : Opponents)
	{
		const ARaceOpponent* Actor = Pair.Value;
		if (!Actor || Actor->bIsGhost) continue;
		const FVector At = RoverloomFrames::UnrealToSitePosition(Actor->GetActorLocation());
		const double D = FVector2D::Distance(FVector2D(At.X, At.Y), FVector2D(You.X, You.Y));
		if (D > 6.0) continue;
		Nearest = FMath::Min(Nearest, D);
		const double Yaw = -FMath::DegreesToRadians(Actor->GetActorRotation().Yaw); // Unreal's Y is the site's -Y
		Line += FString::Printf(TEXT(" %s@%.3f,%.3f,%.4f"), *Pair.Key, At.X, At.Y, Yaw);
	}
	if (Nearest > 6.0) return;
	UE_LOG(LogRoverloom, Display, TEXT("%s"), *Line);
	if (Nearest < 3.2 && RaceShots < 12 && NowS - RaceShotLastS >= 1.5)
	{
		RaceShotLastS = NowS;
		++RaceShots;
		const FString Name = FString::Printf(TEXT("contact-%02d-t%.0f.png"), RaceShots, NowS - MissionClockStartS);
		FScreenshotRequest::RequestScreenshot(FPaths::Combine(RaceDiagnoseDir, Name), true, false);
		UE_LOG(LogRoverloom, Display, TEXT("RaceDraw screenshot %s"), *Name);
	}
}

void ARoverPawn::MissionLinkStart()
{
	ISocketSubsystem* Sockets = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM);
	TSharedRef<FInternetAddr> Address = Sockets->CreateInternetAddr();
	bool bValid = false;
	Address->SetIp(TEXT("127.0.0.1"), bValid); // Loopback only, never another interface
	Address->SetPort(8100);
	LinkListen = Sockets->CreateSocket(NAME_Stream, TEXT("RoverMissionLink"), false);
	if (!LinkListen || !bValid || !LinkListen->SetReuseAddr(true) || !LinkListen->SetNonBlocking(true) || !LinkListen->Bind(*Address)
		|| !LinkListen->Listen(1))
	{
		UE_LOG(LogRoverloom, Error, TEXT("Rover mission link: cannot listen on 127.0.0.1:8100"));
		MissionLinkStop();
		Status.MissionLine = TEXT("Mission (Python): link failed to open");
		return;
	}
	Status.MissionLine = TEXT("Mission (Python): waiting for the Mission Core");
	UE_LOG(LogRoverloom, Display, TEXT("Rover mission link listening on 127.0.0.1:8100"));
}

void ARoverPawn::MissionLinkDrop(const TCHAR* Why)
{
	RallyDriveScale = 0.0;
	if (LinkClient)
	{
		LinkClient->Close();
		ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(LinkClient);
		LinkClient = nullptr;
	}
	LinkBuffer.Reset();
	if (Router)
	{
		Router->SetActive(KeyboardSource); // Handover after a lost agent starts from a stop; the watchdog covers the rest
	}
	UE_LOG(LogRoverloom, Display, TEXT("Rover mission link: client dropped (%s)"), Why);
	if (!Status.bMissionEnded)
	{
		Status.MissionLine = TEXT("Mission (Python): link lost; waiting");
	}
}

void ARoverPawn::MissionLinkStop()
{
	MissionLinkDrop(TEXT("stop"));
	if (LinkListen)
	{
		LinkListen->Close();
		ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(LinkListen);
		LinkListen = nullptr;
	}
}

void ARoverPawn::MissionLinkTick(double NowS)
{
	// Non-blocking calls on the game thread; the contract asks for a socket thread (backlog). Bad input or a lost
	// client drops the client and never touches the simulation.
	if (!LinkListen)
	{
		return;
	}
	if (!LinkClient)
	{
		bool bPending = false;
		if (LinkListen->HasPendingConnection(bPending) && bPending)
		{
			LinkClient = LinkListen->Accept(TEXT("RoverMissionClient"));
			if (LinkClient)
			{
				LinkClient->SetNonBlocking(true);
				UE_LOG(LogRoverloom, Display, TEXT("Rover mission link: Mission Core connected"));
			}
		}
		if (!LinkClient)
		{
			return;
		}
	}
	if (bRigReady && NowS - LinkLastSendS >= 0.1)
	{
		LinkLastSendS = NowS;
		const FVector P = Status.SitePositionM;
		// Physical rivals: where Unreal's physics has them, for Python's gates, positions and steering
		FString Rivals;
		for (const TPair<FString, TObjectPtr<ARaceOpponent>>& Pair : Opponents)
		{
			FVector2D RivalM;
			double RivalYaw = 0.0, RivalMps = 0.0;
			if (Pair.Value && Pair.Value->IsPhysical() && Pair.Value->GetSitePose(RivalM, RivalYaw, RivalMps))
			{
				const double* Clear = Pair.Value->GetClearance(); // left, ahead, right
				Rivals += FString::Printf(TEXT("%s{\"id\":\"%s\",\"position_m\":[%.4f,%.4f],\"yaw_rad\":%.5f,\"forward_mps\":%.4f,\"clear_m\":[%.2f,%.2f,%.2f]}"),
					Rivals.IsEmpty() ? TEXT("") : TEXT(","), *Pair.Key, RivalM.X, RivalM.Y, RivalYaw, RivalMps, Clear[0], Clear[1], Clear[2]);
			}
		}
		const FString Line = FString::Printf(TEXT("{\"type\":\"telemetry\",\"body\":{\"time_s\":%.3f,\"position_m\":[%.4f,%.4f,%.4f],\"yaw_rad\":%.5f,\"forward_mps\":%.4f,\"resets\":%d,\"boost_requested\":%s,\"opponents\":[%s]}}\n"),
			NowS - MissionClockStartS, P.X, P.Y, P.Z, Status.YawRad, Status.ForwardMps, Status.Resets, (GetWorld()->GetFirstPlayerController() && GetWorld()->GetFirstPlayerController()->IsInputKeyDown(EKeys::SpaceBar)) ? TEXT("true") : TEXT("false"), *Rivals);
		const FTCHARToUTF8 Utf8(*Line);
		int32 Sent = 0;
		if (!LinkClient->Send(reinterpret_cast<const uint8*>(Utf8.Get()), Utf8.Length(), Sent) || Sent != Utf8.Length())
		{
			MissionLinkDrop(TEXT("send failed"));
			return;
		}
	}
	uint32 PendingBytes = 0;
	while (LinkClient && LinkClient->HasPendingData(PendingBytes) && PendingBytes > 0)
	{
		TArray<uint8> Bytes;
		Bytes.SetNumUninitialized(FMath::Min<uint32>(PendingBytes, 65536));
		int32 Read = 0;
		if (!LinkClient->Recv(Bytes.GetData(), Bytes.Num(), Read) || Read <= 0)
		{
			MissionLinkDrop(TEXT("receive failed"));
			return;
		}
		const FUTF8ToTCHAR Text(reinterpret_cast<const ANSICHAR*>(Bytes.GetData()), Read);
		LinkBuffer.Append(Text.Get(), Text.Length());
		if (LinkBuffer.Len() > 1024 * 1024)
		{
			MissionLinkDrop(TEXT("line over 1 MiB"));
			return;
		}
	}
	if (LinkClient && LinkClient->GetConnectionState() == SCS_ConnectionError)
	{
		MissionLinkDrop(TEXT("connection error"));
		return;
	}
	int32 NewLine = INDEX_NONE;
	while (LinkBuffer.FindChar(TEXT('\n'), NewLine))
	{
		const FString Line = LinkBuffer.Left(NewLine);
		LinkBuffer.RightChopInline(NewLine + 1);
		TSharedPtr<FJsonObject> Message;
		FString Type;
		const TSharedPtr<FJsonObject>* Body = nullptr;
		if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Line), Message) || !Message.IsValid()
			|| !Message->TryGetStringField(TEXT("type"), Type) || !Message->TryGetObjectField(TEXT("body"), Body))
		{
			continue; // Ignored, never fatal
		}
		if (Type == TEXT("action"))
		{
			// Bridge v1 `action` (schemas/action.schema.json): body-frame m/s and rad/s, positive yaw turning left.
			// Contract units, so no conversion. The router clamps and refuses non-finite values; a held key wins.
			FAction Requested;
			if (!(*Body)->TryGetNumberField(TEXT("linear_velocity_mps"), Requested.LinearVelocityMps)
				|| !(*Body)->TryGetNumberField(TEXT("yaw_rate_radps"), Requested.YawRateRadps) || bKeyboardHeld)
			{
				continue;
			}
			Router->SetActive(AgentSource);
			Status.bClamped = Router->Submit(AgentSource, Requested, NowS).bClamped;
			continue;
		}
		if (Type != TEXT("mission_state"))
		{
			continue;
		}
		if (bRally)
		{
			RallyStateReceivedS = NowS;
			double Scale = 0.0;
			(*Body)->TryGetNumberField(TEXT("drive_scale"), Scale);
			RallyDriveScale = FMath::IsFinite(Scale) ? FMath::Clamp(Scale, 0.0, 1.5) : 0.0;
			const TArray<TSharedPtr<FJsonValue>>* Targets = nullptr;
			if ((*Body)->TryGetArrayField(TEXT("targets"), Targets))
			{
				for (int32 I = 0; I < FMath::Min(Targets->Num(), 2); ++I)
				{
					const TArray<TSharedPtr<FJsonValue>>& P = (*Targets)[I]->AsArray();
					if (P.Num() == 2 && Status.bRace)
					{
						Status.NextCheckpointM = FVector2D(P[0]->AsNumber(), P[1]->AsNumber());
						Status.bHasNextCheckpoint = true;
					}
					else if (P.Num() == 2) DrawDebugSphere(GetWorld(), RoverloomFrames::SiteToUnrealPosition(FVector(P[0]->AsNumber(), P[1]->AsNumber(), 0)), 200, 24, FColor::Green, false, 0.15f, 0, 3);
				}
			}
			const TSharedPtr<FJsonObject>* Race = nullptr;
			if (Status.bRace && (*Body)->TryGetObjectField(TEXT("race"), Race))
			{
				ReadRaceState(*Race, NowS);
			}
			const TArray<TSharedPtr<FJsonValue>>* Ghost = nullptr;
			if ((*Body)->TryGetArrayField(TEXT("ghost_position_m"), Ghost) && Ghost->Num() == 3)
			{
				const FVector P = RoverloomFrames::SiteToUnrealPosition(FVector((*Ghost)[0]->AsNumber(), (*Ghost)[1]->AsNumber(), (*Ghost)[2]->AsNumber()));
				DrawDebugBox(GetWorld(), P, FVector(100, 75, 20), FColor::Cyan, false, 0.15f, 0, 3);
			}
		}
		const FString Outcome = (*Body)->GetStringField(TEXT("outcome"));
		Status.bMissionEnded = Outcome != TEXT("running");
		Status.MissionLine = FString::Printf(TEXT("Mission (Python): %s   targets %d/%d   %s   t %.1f s"),
			*(*Body)->GetStringField(TEXT("scenario")), static_cast<int32>((*Body)->GetNumberField(TEXT("targets_reached"))),
			static_cast<int32>((*Body)->GetNumberField(TEXT("targets_total"))), *Outcome.ToUpper(), (*Body)->GetNumberField(TEXT("time_s")));
		FString RallyLine;
		if (bRally && (*Body)->TryGetStringField(TEXT("rally_line"), RallyLine)) Status.RallyLine = RallyLine;
		const FString Key = FString::Printf(TEXT("%d %s"), static_cast<int32>((*Body)->GetNumberField(TEXT("targets_reached"))), *Outcome);
		if (Key != LinkLastLogged)
		{
			LinkLastLogged = Key;
			UE_LOG(LogRoverloom, Display, TEXT("Rover mission state from the Mission Core: %s"), *Status.MissionLine);
		}
		if (Status.bMissionEnded && !bMissionShotTaken && !ShotDir.IsEmpty())
		{
			bMissionShotTaken = true; // The HUD shows the verdict from the next frame on
			FScreenshotRequest::RequestScreenshot(FPaths::Combine(ShotDir, TEXT("Mission.png")), true, false);
			UE_LOG(LogRoverloom, Display, TEXT("Rover mission verdict captured: Mission.png"));
		}
	}
}

void ARoverPawn::ReadRaceState(const TSharedPtr<FJsonObject>& Race, double NowS)
{
	Status.bRaceState = true;
	auto Int = [&Race](const TCHAR* Key) { double V = 0.0; Race->TryGetNumberField(Key, V); return FMath::IsFinite(V) ? static_cast<int32>(V) : 0; };
	auto Color = [](const TSharedPtr<FJsonObject>& O)
	{
		const TArray<TSharedPtr<FJsonValue>>* C = nullptr;
		if (O->TryGetArrayField(TEXT("color"), C) && C->Num() == 3)
		{
			return FLinearColor(FMath::Clamp((*C)[0]->AsNumber(), 0.0, 1.0), FMath::Clamp((*C)[1]->AsNumber(), 0.0, 1.0), FMath::Clamp((*C)[2]->AsNumber(), 0.0, 1.0));
		}
		return FLinearColor::White;
	};
	Status.RaceLap = Int(TEXT("lap"));
	Status.RaceLaps = Int(TEXT("laps"));
	Status.RacePosition = Int(TEXT("position"));
	Status.RaceRacers = Int(TEXT("racers"));
	Status.RaceBoosts = Int(TEXT("boosts"));
	Status.RaceFlag = Int(TEXT("flag"));
	Status.RaceFlags = Int(TEXT("flags"));
	Race->TryGetStringField(TEXT("time"), Status.RaceTime);
	Race->TryGetStringField(TEXT("best_lap"), Status.RaceBestLap);
	Race->TryGetStringField(TEXT("banner"), Status.RaceBanner);
	Race->TryGetStringField(TEXT("message"), Status.RaceMessage);
	Race->TryGetStringField(TEXT("controller"), Status.RaceController);
	Race->TryGetNumberField(TEXT("charge"), Status.RaceCharge);
	Status.RaceCharge = FMath::IsFinite(Status.RaceCharge) ? FMath::Clamp(Status.RaceCharge, 0.0, 1.0) : 0.0;
	Race->TryGetBoolField(TEXT("boosting"), Status.bRaceBoosting);
	Race->TryGetBoolField(TEXT("in_sand"), Status.bRaceSand);
	Race->TryGetBoolField(TEXT("dust"), Status.bRaceDust);
	Race->TryGetBoolField(TEXT("dust_warning"), Status.bRaceDustWarning);
	const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
	if (Race->TryGetArrayField(TEXT("standings"), List))
	{
		Status.Standings.Reset();
		for (int32 I = 0; I < FMath::Min(List->Num(), 12); ++I)
		{
			const TSharedPtr<FJsonObject>* Row = nullptr;
			if (!(*List)[I]->TryGetObject(Row)) continue;
			FRoverStatus::FStanding S;
			double Pos = 0.0, Lap = 0.0;
			(*Row)->TryGetNumberField(TEXT("pos"), Pos);
			(*Row)->TryGetNumberField(TEXT("lap"), Lap);
			S.Pos = static_cast<int32>(Pos);
			S.Lap = static_cast<int32>(Lap);
			(*Row)->TryGetStringField(TEXT("name"), S.Name);
			(*Row)->TryGetStringField(TEXT("kind"), S.Kind);
			(*Row)->TryGetStringField(TEXT("gap"), S.Gap);
			(*Row)->TryGetBoolField(TEXT("is_you"), S.bIsYou);
			S.Color = Color(*Row);
			Status.Standings.Add(S);
		}
	}
	TSet<FString> Seen;
	if (Race->TryGetArrayField(TEXT("opponents"), List))
	{
		for (int32 I = 0; I < FMath::Min(List->Num(), 12); ++I)
		{
			const TSharedPtr<FJsonObject>* Row = nullptr;
			const TArray<TSharedPtr<FJsonValue>>* P = nullptr;
			FString Id, Name, Kind;
			double Yaw = 0.0, Pos = 0.0;
			if (!(*List)[I]->TryGetObject(Row) || !(*Row)->TryGetStringField(TEXT("id"), Id) || !(*Row)->TryGetArrayField(TEXT("position_m"), P)
				|| P->Num() < 2)
			{
				continue;
			}
			(*Row)->TryGetStringField(TEXT("name"), Name);
			(*Row)->TryGetStringField(TEXT("kind"), Kind);
			(*Row)->TryGetNumberField(TEXT("yaw_rad"), Yaw);
			(*Row)->TryGetNumberField(TEXT("pos"), Pos);
			const FVector2D At((*P)[0]->AsNumber(), (*P)[1]->AsNumber());
			if (!FMath::IsFinite(At.X) || !FMath::IsFinite(At.Y) || !FMath::IsFinite(Yaw)) continue;
			TObjectPtr<ARaceOpponent>& Actor = Opponents.FindOrAdd(Id);
			if (!Actor)
			{
				FActorSpawnParameters Params;
				Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
				Actor = GetWorld()->SpawnActor<ARaceOpponent>(ARaceOpponent::StaticClass(), FTransform::Identity, Params);
			}
			if (Actor)
			{
				Actor->DisplayName = Name;
				Actor->Position = static_cast<int32>(Pos);
				Actor->LastUpdateS = NowS;
				Actor->SetTarget(At, Yaw, Color(*Row), Kind == TEXT("ghost"));
				// A physical rival: Python drives it (speed, turn rate) and Unreal's physics places it
				const TArray<TSharedPtr<FJsonValue>>* Command = nullptr;
				if (Kind == TEXT("npc") && (*Row)->TryGetArrayField(TEXT("command"), Command) && Command->Num() == 2)
				{
					Actor->EnablePhysics();
					Actor->SetCommand((*Command)[0]->AsNumber(), (*Command)[1]->AsNumber());
					const TArray<TSharedPtr<FJsonValue>>* Reset = nullptr;
					double ResetId = 0.0;
					if ((*Row)->TryGetNumberField(TEXT("reset_id"), ResetId) && static_cast<int32>(ResetId) != Actor->LastResetId
						&& (*Row)->TryGetArrayField(TEXT("reset"), Reset) && Reset->Num() == 3)
					{
						Actor->LastResetId = static_cast<int32>(ResetId);
						Actor->ResetTo(FVector2D((*Reset)[0]->AsNumber(), (*Reset)[1]->AsNumber()), (*Reset)[2]->AsNumber());
						UE_LOG(LogRoverloom, Display, TEXT("Race: %s reset to the course by Python"), *Name);
					}
				}
				Seen.Add(Id);
			}
		}
	}
	for (auto It = Opponents.CreateIterator(); It; ++It)
	{
		if (!Seen.Contains(It.Key()))
		{
			if (It.Value()) It.Value()->Destroy();
			It.RemoveCurrent();
		}
	}
}

void ARoverPawn::DriveScriptCommand(double NowS)
{
	if (DrivePhases.IsEmpty() || DriveIndex >= DrivePhases.Num())
	{
		return;
	}
	if (DriveIndex < 0 || NowS - DrivePhaseStartS >= DrivePhases[DriveIndex].Seconds)
	{
		++DriveIndex;
		DrivePhaseStartS = NowS;
		DriveStartCm = Rig->GetBody()->GetComponentLocation();
		DriveStartForward = Rig->GetBody()->GetForwardVector().GetSafeNormal2D();
		DriveTimeS = DriveDistanceAlongM = DriveHeadingRad = DriveMaxTiltDeg = 0.0;
		DriveMinWheels = 6;
		DriveStartResets = Status.Resets;
		DriveClampedFrames = DriveFrames = 0;
		DriveSpinRatioSum = DriveDiffRatioSum = 0.0;
		DriveSpinSamples = DriveDiffSamples = 0;
		if (DriveIndex >= DrivePhases.Num())
		{
			UE_LOG(LogRoverloom, Display, TEXT("Rover drive script done"));
			return;
		}
	}
	const FDrivePhase& Phase = DrivePhases[DriveIndex];
	FAction Requested;
	Requested.LinearVelocityMps = Phase.LinearMps;
	Requested.YawRateRadps = Phase.YawRadps;
	Status.bClamped = Router->Submit(KeyboardSource, Requested, NowS).bClamped;
}

void ARoverPawn::DriveScriptSample(double NowS, double StepDt)
{
	if (DriveIndex < 0 || DriveIndex >= DrivePhases.Num())
	{
		return;
	}
	const FDrivePhase& Phase = DrivePhases[DriveIndex];
	DriveTimeS += StepDt;
	DriveDistanceAlongM += Status.ForwardMps * StepDt;
	DriveHeadingRad += Status.YawRateRadps * StepDt;
	DriveMaxTiltDeg = FMath::Max(DriveMaxTiltDeg, Status.TiltDeg);
	DriveMinWheels = FMath::Min(DriveMinWheels, Status.WheelsInContact);
	DriveClampedFrames += Status.bClamped ? 1 : 0;
	++DriveFrames;
	{
		const TArray<AWheelRig::FWheelRecord>& Records = Rig->GetRecords();
		double Left = 0.0, Right = 0.0, LeftTarget = 0.0, RightTarget = 0.0;
		for (int32 Index = 0; Index < Records.Num(); ++Index)
		{
			const AWheelRig::FWheelRecord& R = Records[Index];
			if (FMath::Abs(R.TargetSpinRadps) > 0.05)
			{
				DriveSpinRatioSum += R.SpinRadps / R.TargetSpinRadps;
				++DriveSpinSamples;
			}
			(Index < 3 ? Left : Right) += R.SpinRadps / 3.0;
			(Index < 3 ? LeftTarget : RightTarget) += R.TargetSpinRadps / 3.0;
		}
		if (FMath::Abs(LeftTarget - RightTarget) > 0.05)
		{
			DriveDiffRatioSum += (Left - Right) / (LeftTarget - RightTarget);
			++DriveDiffSamples;
		}
	}
	if (NowS + StepDt - DrivePhaseStartS < Phase.Seconds)
	{
		return;
	}
	// Last frame of the phase: commanded against measured, in SI units.
	const double T = FMath::Max(DriveTimeS, 1e-6);
	// Ground-plane displacement from the phase start, split along and across the heading the phase started with.
	FVector DeltaCm = Rig->GetBody()->GetComponentLocation() - DriveStartCm;
	DeltaCm.Z = 0.0;
	const double AlongM = FVector::DotProduct(DeltaCm, DriveStartForward) / RoverloomFrames::UnrealCmPerM;
	const double AcrossM = (DeltaCm - FVector::DotProduct(DeltaCm, DriveStartForward) * DriveStartForward).Size() / RoverloomFrames::UnrealCmPerM;
	UE_LOG(LogRoverloom, Display,
		TEXT("Rover drive phase %s: %.2f s, cmd v %.3f m/s yaw %.4f rad/s; mean v %.3f m/s (%.0f%%), mean yaw %.4f rad/s (%.0f%%), "
			 "net along %.3f m across %.3f m, heading %.1f deg, max tilt %.2f deg, min wheels %d/6, clamped %d/%d frames, resets %d, "
			 "wheel spin/target %.0f%%, left-right spin difference/target %.0f%%, height %.3f m"),
		*Phase.Name, DriveTimeS, Phase.LinearMps, Phase.YawRadps, DriveDistanceAlongM / T,
		Phase.LinearMps != 0.0 ? 100.0 * DriveDistanceAlongM / T / Phase.LinearMps : 0.0, DriveHeadingRad / T,
		Phase.YawRadps != 0.0 ? 100.0 * DriveHeadingRad / T / Phase.YawRadps : 0.0, AlongM, AcrossM,
		FMath::RadiansToDegrees(DriveHeadingRad),
		DriveMaxTiltDeg, DriveMinWheels, DriveClampedFrames, DriveFrames, Status.Resets - DriveStartResets,
		DriveSpinSamples ? 100.0 * DriveSpinRatioSum / DriveSpinSamples : 0.0,
		DriveDiffSamples ? 100.0 * DriveDiffRatioSum / DriveDiffSamples : 0.0, Status.SitePositionM.Z);
}

void ARoverPawn::RecordFrame(double DeltaSeconds)
{
	// Wall time between frames, and the engine's own last-frame thread and GPU times.
	const double NowS = FPlatformTime::Seconds();
	if (WindowStartS < 0.0)
	{
		WindowStartS = NowS;
		return;
	}
	FrameMs.Add(1000.0 * DeltaSeconds);
	GameMsSum += FPlatformTime::ToMilliseconds(GGameThreadTime);
	RenderMsSum += FPlatformTime::ToMilliseconds(GRenderThreadTime);
	GpuMsSum += FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles());
	FocusFrames += FApp::HasFocus() ? 1 : 0;
	if (NowS - WindowStartS < 10.0)
	{
		return;
	}
	const int32 Count = FrameMs.Num();
	double Sum = 0.0;
	for (const double Ms : FrameMs)
	{
		Sum += Ms;
	}
	FrameMs.Sort();
	Status.FrameMsMean = Sum / Count;
	Status.FrameMsP95 = FrameMs[FMath::Min(Count - 1, FMath::FloorToInt32(0.95 * Count))];
	Status.FocusShare = static_cast<double>(FocusFrames) / Count;
	UE_LOG(LogRoverloom, Display,
		TEXT("Rover frames: %d in %.1f s, %.1f fps, frame ms mean %.2f p95 %.2f max %.2f, game %.2f, render %.2f, GPU %.2f, focus %.0f%%, camera %s"),
		Count, NowS - WindowStartS, Count / (NowS - WindowStartS), Status.FrameMsMean, Status.FrameMsP95, FrameMs.Last(), GameMsSum / Count,
		RenderMsSum / Count, GpuMsSum / Count, 100.0 * Status.FocusShare, CameraName(Camera));
	FrameMs.Reset();
	GameMsSum = RenderMsSum = GpuMsSum = 0.0;
	FocusFrames = 0;
	WindowStartS = NowS;
}

void ARoverPawn::LogRenderSettings(const TCHAR* When) const
{
	// The effective values, after the command line, -ExecCmds, and scalability have all applied.
	static const TCHAR* Names[] = {TEXT("r.VSync"), TEXT("t.MaxFPS"), TEXT("r.DynamicGlobalIlluminationMethod"), TEXT("r.ReflectionMethod"),
		TEXT("r.Lumen.HardwareRayTracing"), TEXT("r.RayTracing"), TEXT("r.Shadow.Virtual.Enable"), TEXT("r.AntiAliasingMethod"),
		TEXT("r.ScreenPercentage"), TEXT("r.ScreenPercentage.Default"), TEXT("r.ScreenPercentage.Default.Desktop.Mode"),
		TEXT("r.DynamicRes.OperationMode"), TEXT("r.Nanite"), TEXT("r.MegaLights.Enable"),
		TEXT("sg.ResolutionQuality"), TEXT("sg.ViewDistanceQuality"), TEXT("sg.AntiAliasingQuality"), TEXT("sg.ShadowQuality"),
		TEXT("sg.GlobalIlluminationQuality"), TEXT("sg.ReflectionQuality"), TEXT("sg.PostProcessQuality"), TEXT("sg.TextureQuality"),
		TEXT("sg.EffectsQuality"), TEXT("sg.FoliageQuality"), TEXT("sg.ShadingQuality")};
	FString Line;
	for (const TCHAR* Name : Names)
	{
		const IConsoleVariable* Variable = IConsoleManager::Get().FindConsoleVariable(Name);
		Line += FString::Printf(TEXT(" %s=%s"), Name, Variable ? *Variable->GetString() : TEXT("absent"));
	}
	FIntPoint Size = FIntPoint::ZeroValue;
	if (GEngine && GEngine->GameViewport && GEngine->GameViewport->Viewport)
	{
		Size = GEngine->GameViewport->Viewport->GetSizeXY();
	}
	// Whether the frame's GPU time excludes idle gaps between command buffers, as reported by the RHI.
	UE_LOG(LogRoverloom, Display, TEXT("Rover render settings (%s): viewport=%dx%d gpu_frame_bubbles_removed=%d gpu_timestamp_bubbles_removed=%d%s"),
		When, Size.X, Size.Y, GRHISupportsFrameCyclesBubblesRemoval ? 1 : 0, GRHISupportsGPUTimestampBubblesRemoval ? 1 : 0, *Line);
}

void ARoverPawn::LogAndCapture(double NowS)
{
	if (ReadyTimeS < 0.0)
	{
		return;
	}
	const double SinceReadyS = NowS - ReadyTimeS;
	if (!bLoggedSettle && SinceReadyS >= 3.0)
	{
		bLoggedSettle = true;
		UE_LOG(LogRoverloom, Display, TEXT("Rover settled: site (%.3f, %.3f, %.3f) m, tilt %.2f deg, speed %.3f m/s, wheels on ground %d/6, resets %d"),
			Status.SitePositionM.X, Status.SitePositionM.Y, Status.SitePositionM.Z, Status.TiltDeg, Status.ForwardMps, Status.WheelsInContact,
			Status.Resets);
	}
	if (BenchSeconds > 0.0)
	{
		if (!bBenchProfiled && SinceReadyS >= BenchSeconds - 3.0)
		{
			// One frame of per-pass GPU timings, printed to the log by the engine.
			bBenchProfiled = true;
			GEngine->Exec(GetWorld(), TEXT("ProfileGPU"));
		}
		if (BenchShotS < 0.0 && SinceReadyS >= BenchSeconds)
		{
			BenchShotS = NowS;
			if (!ShotDir.IsEmpty())
			{
				FScreenshotRequest::RequestScreenshot(FPaths::Combine(ShotDir, TEXT("Chase.png")), true, false);
			}
		}
		else if (BenchShotS >= 0.0 && NowS - BenchShotS >= 2.0)
		{
			LogRenderSettings(TEXT("end"));
			UE_LOG(LogRoverloom, Display, TEXT("Rover bench finished after %.1f s"), SinceReadyS);
			BenchSeconds = 0.0;
			ShotStep = 7;
			FPlatformMisc::RequestExit(false, TEXT("RoverBench"));
		}
		return;
	}
	// Each camera is chosen at 12, 14, and 16 s, and captured 1 s later, after it has rendered. The first 10 s frame
	// window has been logged by then, so the HUD's frame line is in the shots.
	if (ShotDir.IsEmpty() || ShotStep >= 7)
	{
		return;
	}
	static const ERoverCamera Shots[3] = {ERoverCamera::Chase, ERoverCamera::Mast, ERoverCamera::Hazard};
	const int32 Index = ShotStep / 2;
	if (Index >= 3)
	{
		SetCamera(ERoverCamera::Chase);
		ShotStep = 7;
		return;
	}
	const bool bCapture = ShotStep % 2 == 1;
	if (SinceReadyS >= 12.0 + 2.0 * Index + (bCapture ? 1.0 : 0.0))
	{
		if (bCapture)
		{
			const FString Name = FString(CameraName(Shots[Index])).Replace(TEXT(", "), TEXT("-")).Replace(TEXT(" "), TEXT("-")).Replace(TEXT("."), TEXT(""));
			const FString Path = FPaths::Combine(ShotDir, Name + TEXT(".png"));
			FScreenshotRequest::RequestScreenshot(Path, true, false);
			UE_LOG(LogRoverloom, Display, TEXT("Rover screenshot requested: %s"), *Path);
		}
		else
		{
			SetCamera(Shots[Index]);
		}
		++ShotStep;
	}
}

void ARoverPawn::FollowBody()
{
	const UStaticMeshComponent* Body = Rig->GetBody();
	SetActorLocationAndRotation(Body->GetComponentLocation(), Body->GetComponentQuat());
}

void ARoverPawn::UpdateWheels(double DeltaSeconds)
{
	// Each wheel sits where its sweep found the ground: the sphere's center is the travel minus the compression below
	// the mount. Without contact it hangs at full travel.
	const TArray<AWheelRig::FWheelRecord>& Records = Rig->GetRecords();
	const double RestCm = Rig->GetParams().RestLengthCm;
	for (int32 Index = 0; Index < NumWheels && Index < Records.Num(); ++Index)
	{
		const AWheelRig::FWheelRecord& Record = Records[Index];
		const double Compression = Record.Contact.bHit ? FMath::Clamp(Record.Contact.CompressionCm, 0.0, RestCm) : 0.0;
		const double Drop = RestCm - Compression;
		const FVector Mount = WheelMountCm(Index);
		const FVector Center = Mount - FVector(0.0, 0.0, Drop);
		WheelAnglesRad[Index] = FMath::Fmod(WheelAnglesRad[Index] + Record.SpinRadps * DeltaSeconds, 2.0 * UE_DOUBLE_PI);
		// Rolling forward turns the wheel's front down, which is a negative pitch about the axle.
		const FQuat Spin(FRotator(-FMath::RadiansToDegrees(WheelAnglesRad[Index]), 0.0, 0.0));
		if (bModelV2)
		{
			// The V2 wheel's axle is already along Y. Struts run inboard of the wheels; axles join them to the hubs.
			Wheels[Index]->SetRelativeLocationAndRotation(Center, Spin);
			Legs[Index]->SetRelativeLocation(FVector(Mount.X, FMath::Sign(Mount.Y) * ModelArmYCm, Mount.Z - Drop / 2.0));
			Legs[Index]->SetRelativeScale3D(FVector(1.0, 1.0, FMath::Max(Drop, 1.0) / 100.0));
			ModelAxles[Index]->SetRelativeLocation(Center);
			continue;
		}
		Wheels[Index]->SetRelativeLocationAndRotation(Center, Spin * FQuat(FRotator(0.0, 0.0, 90.0)));
		WheelMarks[Index]->SetRelativeLocationAndRotation(Center, Spin);
		Legs[Index]->SetRelativeLocation(Mount - FVector(0.0, 0.0, Drop / 2.0));
		Legs[Index]->SetRelativeScale3D(FVector(0.06, 0.06, FMath::Max(Drop, 1.0) / 100.0));
	}
}

void ARoverPawn::UpdateFreeCamera(double DeltaSeconds)
{
	if (Camera != ERoverCamera::Free || !FreeCamera)
	{
		return;
	}
	const FRotator View = FreeCamera->GetActorRotation();
	const FRotationMatrix Axes(View);
	const FVector Move = Axes.GetUnitAxis(EAxis::X) * FreeMove.Y + Axes.GetUnitAxis(EAxis::Y) * FreeMove.X;
	FreeCamera->AddActorWorldOffset(Move * FreeCameraSpeedCmps * DeltaSeconds + FVector(0.0, 0.0, FreeLift * FreeCameraLiftCmps * DeltaSeconds));
}

void ARoverPawn::SetCamera(ERoverCamera NewCamera)
{
	APlayerController* Controller = Cast<APlayerController>(GetController());
	if (NewCamera == ERoverCamera::Free && Controller)
	{
		// Start the free camera where the current view is.
		const FVector Eye = Controller->PlayerCameraManager ? Controller->PlayerCameraManager->GetCameraLocation() : GetActorLocation();
		const FRotator Look = Controller->PlayerCameraManager ? Controller->PlayerCameraManager->GetCameraRotation() : GetActorRotation();
		if (!FreeCamera)
		{
			FActorSpawnParameters SpawnParams;
			SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			FreeCamera = GetWorld()->SpawnActor<ACameraActor>(Eye, FRotator(Look.Pitch, Look.Yaw, 0.0), SpawnParams);
		}
		else
		{
			FreeCamera->SetActorLocationAndRotation(Eye, FRotator(Look.Pitch, Look.Yaw, 0.0));
		}
	}
	Camera = NewCamera;
	ChaseCamera->SetActive(Camera == ERoverCamera::Chase);
	MastCamera->SetActive(Camera == ERoverCamera::Mast);
	HazardCamera->SetActive(Camera == ERoverCamera::Hazard);
	if (Controller)
	{
		if (Camera == ERoverCamera::Free && FreeCamera)
		{
			Controller->SetViewTarget(FreeCamera);
		}
		else
		{
			Controller->SetViewTarget(this);
		}
	}
	Status.Camera = Camera;
	UE_LOG(LogRoverloom, Display, TEXT("Rover camera: %s"), CameraName(Camera));
}

void ARoverPawn::CreateInput()
{
	// Actions and keys are built here, so that no input asset is needed yet.
	Mapping = NewObject<UInputMappingContext>(this, TEXT("RoverMapping"));
	auto MakeAction = [this](const TCHAR* Name, EInputActionValueType Type)
	{
		UInputAction* Action = NewObject<UInputAction>(this, Name);
		Action->ValueType = Type;
		return Action;
	};
	DriveAction = MakeAction(TEXT("Drive"), EInputActionValueType::Axis1D);
	TurnAction = MakeAction(TEXT("Turn"), EInputActionValueType::Axis1D);
	CameraAction = MakeAction(TEXT("NextCamera"), EInputActionValueType::Boolean);
	ResetAction = MakeAction(TEXT("Reset"), EInputActionValueType::Boolean);
	LookAction = MakeAction(TEXT("Look"), EInputActionValueType::Axis2D);
	FreeMoveAction = MakeAction(TEXT("FreeMove"), EInputActionValueType::Axis2D);
	FreeLiftAction = MakeAction(TEXT("FreeLift"), EInputActionValueType::Axis1D);

	auto Map = [this](UInputAction* Action, const FKey& Key, bool bNegate, bool bSwizzle)
	{
		FEnhancedActionKeyMapping& KeyMapping = Mapping->MapKey(Action, Key);
		if (bSwizzle)
		{
			KeyMapping.Modifiers.Add(NewObject<UInputModifierSwizzleAxis>(Mapping)); // X to Y
		}
		if (bNegate)
		{
			KeyMapping.Modifiers.Add(NewObject<UInputModifierNegate>(Mapping));
		}
	};
	Map(DriveAction, EKeys::W, false, false);
	Map(DriveAction, EKeys::S, true, false);
	Map(TurnAction, EKeys::A, false, false); // Left is positive, as the contract
	Map(TurnAction, EKeys::D, true, false);
	Map(CameraAction, EKeys::C, false, false);
	Map(ResetAction, EKeys::R, false, false);
	Map(LookAction, EKeys::Mouse2D, false, false);
	Map(FreeMoveAction, EKeys::Up, false, true);
	Map(FreeMoveAction, EKeys::Down, true, true);
	Map(FreeMoveAction, EKeys::Right, false, false);
	Map(FreeMoveAction, EKeys::Left, true, false);
	Map(FreeLiftAction, EKeys::PageUp, false, false);
	Map(FreeLiftAction, EKeys::PageDown, true, false);
	const FKey GearKeys[] = {EKeys::E, EKeys::Q, EKeys::One, EKeys::Two, EKeys::Three};
	for (const FKey& Key : GearKeys)
	{
		UInputAction* Action = MakeAction(*FString::Printf(TEXT("Gear%s"), *Key.ToString()), EInputActionValueType::Boolean);
		GearActions.Add(Action);
		Map(Action, Key, false, false);
	}
}

void ARoverPawn::AddMappingContext()
{
	const APlayerController* Controller = Cast<APlayerController>(GetController());
	const ULocalPlayer* LocalPlayer = Controller ? Controller->GetLocalPlayer() : nullptr;
	if (UEnhancedInputLocalPlayerSubsystem* Subsystem = LocalPlayer ? LocalPlayer->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>() : nullptr)
	{
		Subsystem->AddMappingContext(Mapping, 0);
	}
}

void ARoverPawn::PawnClientRestart()
{
	Super::PawnClientRestart();
	if (!Mapping)
	{
		CreateInput();
	}
	AddMappingContext();
	SetCamera(Camera);
}

void ARoverPawn::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);
	if (!Mapping)
	{
		CreateInput();
	}
	UEnhancedInputComponent* Input = Cast<UEnhancedInputComponent>(PlayerInputComponent);
	if (!Input)
	{
		UE_LOG(LogRoverloom, Error, TEXT("RoverPawn needs EnhancedInputComponent; check DefaultInput.ini"));
		return;
	}
	Input->BindAction(DriveAction, ETriggerEvent::Triggered, this, &ARoverPawn::OnDrive);
	Input->BindAction(DriveAction, ETriggerEvent::Completed, this, &ARoverPawn::OnDriveReleased);
	Input->BindAction(TurnAction, ETriggerEvent::Triggered, this, &ARoverPawn::OnTurn);
	Input->BindAction(TurnAction, ETriggerEvent::Completed, this, &ARoverPawn::OnTurnReleased);
	Input->BindAction(CameraAction, ETriggerEvent::Started, this, &ARoverPawn::OnNextCamera);
	Input->BindAction(ResetAction, ETriggerEvent::Started, this, &ARoverPawn::OnReset);
	if (GearActions.Num() == 5)
	{
		Input->BindAction(GearActions[0], ETriggerEvent::Started, this, &ARoverPawn::OnGearUp);
		Input->BindAction(GearActions[1], ETriggerEvent::Started, this, &ARoverPawn::OnGearDown);
		Input->BindAction(GearActions[2], ETriggerEvent::Started, this, &ARoverPawn::OnGear1);
		Input->BindAction(GearActions[3], ETriggerEvent::Started, this, &ARoverPawn::OnGear2);
		Input->BindAction(GearActions[4], ETriggerEvent::Started, this, &ARoverPawn::OnGear3);
	}
	Input->BindAction(LookAction, ETriggerEvent::Triggered, this, &ARoverPawn::OnLook);
	Input->BindAction(FreeMoveAction, ETriggerEvent::Triggered, this, &ARoverPawn::OnFreeMove);
	Input->BindAction(FreeMoveAction, ETriggerEvent::Completed, this, &ARoverPawn::OnFreeMoveReleased);
	Input->BindAction(FreeLiftAction, ETriggerEvent::Triggered, this, &ARoverPawn::OnFreeLift);
	Input->BindAction(FreeLiftAction, ETriggerEvent::Completed, this, &ARoverPawn::OnFreeLiftReleased);
}

void ARoverPawn::OnDrive(const FInputActionValue& Value)
{
	DriveInput = FMath::Clamp(static_cast<double>(Value.Get<float>()), -1.0, 1.0);
	bKeyboardHeld = true;
}

void ARoverPawn::OnDriveReleased(const FInputActionValue& Value)
{
	DriveInput = 0.0;
	if (TurnInput == 0.0 && bKeyboardHeld)
	{
		// Releasing every key is a deliberate stop, sent once; the watchdog then expires 2 s later.
		bKeyboardHeld = false;
		Router->Submit(KeyboardSource, FAction(), GetWorld()->GetTimeSeconds());
	}
}

void ARoverPawn::OnTurn(const FInputActionValue& Value)
{
	TurnInput = FMath::Clamp(static_cast<double>(Value.Get<float>()), -1.0, 1.0);
	bKeyboardHeld = true;
}

void ARoverPawn::OnTurnReleased(const FInputActionValue& Value)
{
	TurnInput = 0.0;
	if (DriveInput == 0.0 && bKeyboardHeld)
	{
		bKeyboardHeld = false;
		Router->Submit(KeyboardSource, FAction(), GetWorld()->GetTimeSeconds());
	}
}

void ARoverPawn::OnNextCamera(const FInputActionValue& Value)
{
	SetCamera(static_cast<ERoverCamera>((static_cast<uint8>(Camera) + 1) % 4));
}

void ARoverPawn::OnGearUp(const FInputActionValue& Value)
{
	SetGear(Status.Gear + 1);
}

void ARoverPawn::OnGearDown(const FInputActionValue& Value)
{
	SetGear(Status.Gear - 1);
}

void ARoverPawn::SetGear(int32 NewGear)
{
	Status.Gear = FMath::Clamp(NewGear, 1, 3);
	UE_LOG(LogRoverloom, Display, TEXT("Rover speed level %d (%.0f%%)"), Status.Gear, 100.0 * GearScale(Status.Gear));
}

void ARoverPawn::OnReset(const FInputActionValue& Value)
{
	ResetRig(TEXT("reset key"));
}

void ARoverPawn::OnLook(const FInputActionValue& Value)
{
	if (Camera != ERoverCamera::Free || !FreeCamera)
	{
		return;
	}
	const FVector2D Delta = Value.Get<FVector2D>();
	FRotator View = FreeCamera->GetActorRotation();
	View.Yaw += Delta.X * LookDegPerUnit;
	View.Pitch = FMath::Clamp(View.Pitch + Delta.Y * LookDegPerUnit, -85.0, 85.0);
	View.Roll = 0.0;
	FreeCamera->SetActorRotation(View);
}

void ARoverPawn::OnFreeMove(const FInputActionValue& Value)
{
	FreeMove = Value.Get<FVector2D>();
}

void ARoverPawn::OnFreeMoveReleased(const FInputActionValue& Value)
{
	FreeMove = FVector2D::ZeroVector;
}

void ARoverPawn::OnFreeLift(const FInputActionValue& Value)
{
	FreeLift = Value.Get<float>();
}

void ARoverPawn::OnFreeLiftReleased(const FInputActionValue& Value)
{
	FreeLift = 0.0;
}
