#include "RoverPawn.h"

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
#include "InputAction.h"
#include "InputActionValue.h"
#include "InputCoreTypes.h"
#include "InputMappingContext.h"
#include "InputModifiers.h"
#include "DynamicRHI.h"
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

#include "../Bridge/Frames.h"
#include "../Roverloom.h"
#include "../WheelSpike/WheelRig.h"
#include "Greybox.h"
#include "RoverDrive.h"

using namespace RoverloomCommand;
using namespace RoverloomRover;

const TCHAR* ARoverPawn::KeyboardSource = TEXT("keyboard");

namespace
{
	// Above this speed the rig has diverged, as WheelSpikeGameMode's "diverged" outcome.
	const double DivergedSpeedCmps = 1000.0;
	const double FreeCameraSpeedCmps = 800.0;
	const double FreeCameraLiftCmps = 400.0;
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

	Router = MakeUnique<FCommandRouter>(TArray<FString>{KeyboardSource}, KeyboardSource, MaxSpeedMps, MaxYawRateRadps);
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
	StartTransform = FTransform(GetActorQuat(), GetActorLocation());
	FParse::Value(FCommandLine::Get(), TEXT("RoverShotDir="), ShotDir);
	FParse::Value(FCommandLine::Get(), TEXT("RoverBench="), BenchSeconds);
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
	SpawnRig();
}

void ARoverPawn::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
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
	Tint(Rig->GetBody(), FLinearColor(0.75f, 0.72f, 0.66f));
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
			bLoggedSettle = false;
			UE_LOG(LogRoverloom, Display, TEXT("Rover rig ready at %.2f s: %d wheels, drive model P (provisional)"), ReadyTimeS, Rig->NumWheels());
			LogRenderSettings(TEXT("start"));
		}
		FollowBody();
		UpdateFreeCamera(DeltaSeconds);
		return;
	}

	const double NowS = GetWorld()->GetTimeSeconds();
	if (bKeyboardHeld)
	{
		FAction Requested;
		Requested.LinearVelocityMps = DriveInput * MaxSpeedMps;
		Requested.YawRateRadps = TurnInput * MaxYawRateRadps;
		Status.bClamped = Router->Submit(KeyboardSource, Requested, NowS).bClamped;
	}
	const FAction Applied = Router->Current(NowS);
	TArray<double> Targets;
	SkidSteerTargets(Applied, Targets);
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
	if (Location.ContainsNaN() || Velocity.ContainsNaN() || Velocity.Size() > DivergedSpeedCmps || Location.Z < -1000.0)
	{
		ResetRig(Location.ContainsNaN() || Velocity.ContainsNaN() ? TEXT("nan") : TEXT("diverged"));
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
	Status.WheelsInContact = 0;
	for (const AWheelRig::FWheelRecord& Record : Rig->GetRecords())
	{
		Status.WheelsInContact += Record.Contact.bHit ? 1 : 0;
	}
	LogAndCapture(NowS);
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
		TEXT("r.ScreenPercentage"), TEXT("r.DynamicRes.OperationMode"), TEXT("r.Nanite"), TEXT("r.MegaLights.Enable"),
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
	UE_LOG(LogRoverloom, Display, TEXT("Rover render settings (%s): viewport=%dx%d%s"), When, Size.X, Size.Y, *Line);
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
