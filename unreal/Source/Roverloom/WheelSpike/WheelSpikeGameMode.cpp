#include "WheelSpikeGameMode.h"

#include "Camera/CameraActor.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/DirectionalLight.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/WorldSettings.h"
#include "HAL/PlatformMisc.h"
#include "HAL/PlatformTime.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/EngineVersion.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "PhysicalMaterials/PhysicalMaterial.h"
#include "PhysicsEngine/BodyInstance.h"

#include "../Roverloom.h"
#include "WheelRig.h"

using namespace RoverloomWheel;

namespace
{
	const double Gravity = 371.0;          // cm/s^2, magnitude
	const double WheelRadiusCm = 25.0;     // pathfinder_6w
	const double HalfTrackCm = 103.7;      // pathfinder_6w
	const double DriveSpinRadps = 2.0;     // 50 cm/s rim speed
	const double TurnRateDegps = 28.178;   // pathfinder_6w's 0.4918 rad/s
	const double SettleS = 2.0;
	const double RideHeightCm = 70.0;      // Body center above ground at 5 cm compression

	// Phase C: pathfinder_6w on one free body. Settling, speeds, and the random seed as in R0.
	const double SixMassKg = 853.5;
	const double SixMountXCm = 97.6;
	const double SixSettleS = 3.0;
	const double SixSpeedCmps = 50.0;
	const int32 SixSeed = 42;
}

AWheelSpikeGameMode::AWheelSpikeGameMode()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = true;
	PrimaryActorTick.TickGroup = TG_PrePhysics;
	DefaultPawnClass = nullptr;
}

void AWheelSpikeGameMode::StartPlay()
{
	Super::StartPlay();

	const TCHAR* CommandLine = FCommandLine::Get();
	FParse::Value(CommandLine, TEXT("WheelScenario="), Scenario);
	if (!FParse::Value(CommandLine, TEXT("SpikeOut="), OutDir))
	{
		OutDir = FPaths::ProjectSavedDir() / TEXT("WheelSpike") / TEXT("manual");
	}

	struct FPlan
	{
		const TCHAR* Id;
		int32 Wheels;
		bool bSweep;
		double Friction;
		double SlopeDeg;
		double DurationS;
	};
	static const FPlan Plans[] = {
		{TEXT("a1"), 1, false, 0.6, 0.0, 6.0},
		{TEXT("a1s"), 1, true, 0.6, 0.0, 6.0},
		{TEXT("a2"), 1, false, 0.6, 0.0, 12.0},
		{TEXT("a2s"), 1, true, 0.6, 0.0, 12.0},
		{TEXT("a3"), 1, false, 0.05, 0.0, 8.0},
		{TEXT("a4"), 1, false, 0.1, 0.0, 11.0},
		{TEXT("a5"), 1, false, 0.3, 0.0, 6.0},
		{TEXT("a6"), 1, false, 0.6, 10.0, 6.0},
		{TEXT("a7"), 1, false, 0.1, 10.0, 6.0},
		{TEXT("b1"), 2, false, 0.6, 0.0, 12.0},
		{TEXT("b2"), 2, false, 0.6, 0.0, 10.0},
		{TEXT("b3"), 2, false, 0.6, 0.0, 11.0},
		{TEXT("b4"), 2, false, 0.6, 10.0, 6.0},
		// Phase C diagnostics, not gated.
		{TEXT("cd_freefall"), 6, true, 0.6, 0.0, 1.4},
		{TEXT("cd_drop"), 6, true, 0.6, 0.0, 8.0},
		{TEXT("cd_tilt"), 6, true, 0.6, 0.0, 8.0},
		{TEXT("cd_slide_brake"), 6, true, 0.3, 0.0, 6.0},
		{TEXT("cd_slide_coast"), 6, true, 0.3, 0.0, 6.0},
		// Phase C tests, and runs reported without a threshold.
		{TEXT("c1"), 6, true, 0.6, 0.0, 15.0},
		{TEXT("c1r"), 6, false, 0.6, 0.0, 15.0},
		{TEXT("c2"), 6, true, 0.6, 0.0, 23.0},
		{TEXT("c3"), 6, true, 0.6, 0.0, 23.0},
		{TEXT("c5"), 6, true, 0.6, 10.0, 10.0},
		{TEXT("c5b"), 6, true, 0.6, 10.0, 10.0},
		{TEXT("c6_5"), 6, true, 0.6, 5.0, 30.0},
		{TEXT("c6_10"), 6, true, 0.6, 10.0, 30.0},
		{TEXT("c6_15"), 6, true, 0.6, 15.0, 30.0},
		{TEXT("c6_20"), 6, true, 0.6, 20.0, 30.0},
		{TEXT("c7"), 6, true, 0.6, 0.0, 600.0},
		{TEXT("cstep_10"), 6, true, 0.6, 0.0, 43.0},
		{TEXT("cstep_25"), 6, true, 0.6, 0.0, 43.0},
		{TEXT("cstep_50"), 6, true, 0.6, 0.0, 43.0},
		{TEXT("cperf"), 6, true, 0.6, 0.0, 63.0},
	};
	const FPlan* Plan = nullptr;
	for (const FPlan& Candidate : Plans)
	{
		if (Scenario == Candidate.Id)
		{
			Plan = &Candidate;
		}
	}
	if (!Plan)
	{
		UE_LOG(LogRoverloom, Error, TEXT("Unknown wheel scenario '%s'"), *Scenario);
		Finish(TEXT("unknown_scenario"));
		return;
	}
	bPair = Plan->Wheels == 2;
	bSix = Plan->Wheels == 6;
	bSweep = Plan->bSweep;
	Friction = Plan->Friction;
	SlopeDeg = Plan->SlopeDeg;
	DurationS = Plan->DurationS;
	if (Scenario.StartsWith(TEXT("cstep_")))
	{
		StepCm = FCString::Atod(*Scenario.RightChop(6));
	}
	Random.Initialize(SixSeed);

	UWorld* World = GetWorld();
	AWorldSettings* Settings = World->GetWorldSettings();
	Settings->bGlobalGravitySet = true;
	Settings->GlobalGravityZ = -Gravity;

	// The model reads friction from its own parameter. The ground's material matters only if the body touches it.
	Material = NewObject<UPhysicalMaterial>(this);
	Material->Friction = Friction;
	Material->StaticFriction = Friction;
	Material->Restitution = 0.0f;

	const FRotator Tilt(SlopeDeg, 0.0, 0.0);
	const FVector Up = Tilt.RotateVector(FVector::UpVector);
	SpawnBlock(-50.0 * Up, Tilt, FVector(20000.0, 20000.0, 100.0));
	if (StepCm > 0.0)
	{
		// R0's step: a block ahead of the start, across the rover's path.
		SpawnBlock(FVector(800.0, 0.0, StepCm / 2.0), FRotator::ZeroRotator, FVector(1000.0, 800.0, StepCm));
	}
	if (Scenario == TEXT("c7"))
	{
		// R0's stability layout: 10 cm blocks away from the start.
		FRandomStream Layout(SixSeed + 1);
		for (int32 Index = 0; Index < 30; ++Index)
		{
			const FVector Center(Layout.FRandRange(-1500.0, 1500.0), Layout.FRandRange(-1500.0, 1500.0), 5.0);
			if (Center.Size2D() > 400.0)
			{
				SpawnBlock(Center, FRotator(0.0, Layout.FRandRange(0.0, 90.0), 0.0), FVector(100.0, 100.0, 10.0));
			}
		}
	}

	FVector Start = RideHeightCm * Up;
	FRotator StartRotation = Tilt;
	if (Scenario == TEXT("cd_freefall"))
	{
		Start.Z = 500.0;
	}
	else if (Scenario == TEXT("cd_drop"))
	{
		Start.Z += 20.0;
	}
	else if (Scenario == TEXT("cd_tilt"))
	{
		Start.Z += 10.0;
		StartRotation = FRotator(2.0, 0.0, 3.0);
	}

	FActorSpawnParameters SpawnParams;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	Rig = World->SpawnActor<AWheelRig>(AWheelRig::StaticClass(), Start, StartRotation, SpawnParams);
	TArray<AWheelRig::FWheelSetup> Wheels;
	if (bSix)
	{
		// Left is -Y in Unreal. Wheels 0-2 are left and 3-5 right, each front, middle, rear.
		for (const double Y : {-HalfTrackCm, HalfTrackCm})
		{
			for (const double X : {SixMountXCm, 0.0, -SixMountXCm})
			{
				Wheels.Add({FVector(X, Y, -20.0), Y < 0.0});
			}
		}
		Rig->Build(FVector(200.0, 150.0, 40.0), SixMassKg, Wheels, false, false, bSweep, Friction, Material);
	}
	else if (bPair)
	{
		Wheels.Add({FVector(0.0, -HalfTrackCm, -20.0), true});
		Wheels.Add({FVector(0.0, HalfTrackCm, -20.0), false});
		Rig->Build(FVector(60.0, 150.0, 40.0), 853.5 / 3.0, Wheels, true, false, bSweep, Friction, Material);
	}
	else
	{
		Wheels.Add({FVector(0.0, 0.0, -20.0), true});
		Rig->Build(FVector(40.0, 40.0, 40.0), 853.5 / 6.0, Wheels, true, true, bSweep, Friction, Material);
	}

	World->SpawnActor<ADirectionalLight>(FVector::ZeroVector, FRotator(-40.0, 30.0, 0.0));
	UE_LOG(LogRoverloom, Display, TEXT("Wheel scenario %s started, gravity %.3f"), *Scenario, World->GetGravityZ());
}

void AWheelSpikeGameMode::SpawnBlock(const FVector& Center, const FRotator& Rotation, const FVector& SizeCm)
{
	AStaticMeshActor* Block = GetWorld()->SpawnActorDeferred<AStaticMeshActor>(AStaticMeshActor::StaticClass(),
		FTransform(Rotation, Center, SizeCm / 100.0), nullptr, nullptr, ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
	UStaticMeshComponent* Mesh = Block->GetStaticMeshComponent();
	Mesh->SetMobility(EComponentMobility::Movable);
	Mesh->SetStaticMesh(LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")));
	Mesh->SetPhysMaterialOverride(Material);
	Block->FinishSpawning(FTransform(Rotation, Center, SizeCm / 100.0));
}

void AWheelSpikeGameMode::Command(double TimeS, TArray<double>& OutTargets, EWheelMode& OutMode, FVector& OutPush)
{
	if (bSix)
	{
		CommandSix(TimeS, OutTargets, OutMode, OutPush);
		return;
	}
	const int32 Count = bPair ? 2 : 1;
	OutTargets.Init(0.0, Count);
	OutMode = EWheelMode::Drive;
	OutPush = FVector::ZeroVector;
	const bool bDriving = TimeS >= SettleS;

	if (Scenario.StartsWith(TEXT("a2")) || Scenario == TEXT("a3") || Scenario == TEXT("b1"))
	{
		OutTargets.Init(bDriving ? DriveSpinRadps : 0.0, Count);
	}
	else if (Scenario == TEXT("a4") || Scenario == TEXT("b3"))
	{
		OutTargets.Init(bDriving && TimeS < 7.0 ? DriveSpinRadps : 0.0, Count);
		if (Scenario == TEXT("a4") && TimeS >= 7.0)
		{
			OutMode = EWheelMode::Brake;
		}
	}
	else if (Scenario == TEXT("a5") && TimeS >= 2.0 && TimeS < 2.5)
	{
		const double Mass = 853.5 / 6.0;
		OutPush = Rig->GetBody()->GetRightVector() * (2.0 * Friction * Mass * Gravity);
	}
	else if (Scenario == TEXT("a6") || Scenario == TEXT("a7"))
	{
		OutMode = EWheelMode::Brake;
	}
	else if (Scenario == TEXT("b2") && bDriving)
	{
		// Unreal yaw rate is positive to the right, so the left wheel runs forward.
		const double Rim = FMath::DegreesToRadians(TurnRateDegps) * HalfTrackCm;
		OutTargets[0] = Rim / WheelRadiusCm;
		OutTargets[1] = -Rim / WheelRadiusCm;
	}
}

void AWheelSpikeGameMode::CommandSix(double TimeS, TArray<double>& OutTargets, EWheelMode& OutMode, FVector& OutPush)
{
	OutTargets.Init(0.0, 6);
	OutMode = EWheelMode::Drive;
	OutPush = FVector::ZeroVector;
	const bool bDriving = TimeS >= SixSettleS;
	double ForwardCmps = 0.0;
	double YawRateDegps = 0.0;

	if (Scenario == TEXT("c2") || Scenario == TEXT("cperf") || Scenario.StartsWith(TEXT("c6_")) || Scenario.StartsWith(TEXT("cstep_")))
	{
		ForwardCmps = bDriving ? SixSpeedCmps : 0.0;
	}
	else if (Scenario == TEXT("c3"))
	{
		YawRateDegps = bDriving ? TurnRateDegps : 0.0;
	}
	else if (Scenario == TEXT("c5b") || Scenario == TEXT("cd_slide_brake"))
	{
		OutMode = EWheelMode::Brake;
	}
	else if (Scenario == TEXT("cd_slide_coast"))
	{
		OutMode = EWheelMode::Coast;
	}
	else if (Scenario == TEXT("c7") && bDriving)
	{
		if (TimeS >= NextRandomChangeS)
		{
			RandomForwardCmps = Random.FRandRange(-SixSpeedCmps, SixSpeedCmps);
			RandomYawRateDegps = Random.FRandRange(-TurnRateDegps, TurnRateDegps);
			NextRandomChangeS = TimeS + 5.0;
		}
		ForwardCmps = RandomForwardCmps;
		YawRateDegps = RandomYawRateDegps;
	}

	// Sliding diagnostics: a diagonal push of twice the friction limit for 0.5 s.
	if (Scenario.StartsWith(TEXT("cd_slide")) && TimeS >= 2.0 && TimeS < 2.5)
	{
		const FVector Diagonal = (Rig->GetBody()->GetForwardVector() + Rig->GetBody()->GetRightVector()).GetSafeNormal();
		OutPush = Diagonal * (2.0 * Friction * SixMassKg * Gravity);
	}

	// Skid steering as in R0: rim speed v plus or minus yaw rate times half track, at 25 cm radius.
	// Unreal yaw rate is positive to the right, so the left side runs faster.
	const double Turn = FMath::DegreesToRadians(YawRateDegps) * HalfTrackCm;
	for (int32 Index = 0; Index < 6; ++Index)
	{
		OutTargets[Index] = (Index < 3 ? ForwardCmps + Turn : ForwardCmps - Turn) / WheelRadiusCm;
	}
}

void AWheelSpikeGameMode::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (bFinished || !Rig)
	{
		return;
	}
	if (!bStarted)
	{
		// Time starts on the frame the body exists and simulates.
		if (!Rig->IsReady())
		{
			return;
		}
		bStarted = true;
		LastWallS = FPlatformTime::Seconds();
		if (APlayerController* Controller = GetWorld()->GetFirstPlayerController())
		{
			const FVector Eye = bSix ? FVector(-1200.0, -900.0, 600.0) : FVector(-600.0, -450.0, 300.0);
			Controller->SetViewTarget(GetWorld()->SpawnActor<ACameraActor>(Eye, FRotator(-20.0, 37.0, 0.0)));
		}
	}
	if (Frame > 0)
	{
		SimTimeS += DeltaSeconds;
	}
	const double NowWallS = FPlatformTime::Seconds();
	const double WallFrameMs = 1000.0 * (NowWallS - LastWallS);
	LastWallS = NowWallS;

	TArray<double> Targets;
	EWheelMode Mode = EWheelMode::Drive;
	FVector Push = FVector::ZeroVector;
	Command(SimTimeS, Targets, Mode, Push);
	Rig->SetTargets(Targets, Mode);
	Rig->SetExternalForce(Push);
	Rig->StepWheels(DeltaSeconds);
	Record(DeltaSeconds, WallFrameMs, Push);
	++Frame;

	const FVector Velocity = Rig->GetBody()->GetPhysicsLinearVelocity();
	if (Rig->GetBody()->GetComponentLocation().ContainsNaN() || Velocity.ContainsNaN())
	{
		Finish(TEXT("nan"));
	}
	else if (Velocity.Size() > 1000.0)
	{
		Finish(TEXT("diverged"));
	}
	else if (SimTimeS >= DurationS)
	{
		Finish(TEXT("completed"));
	}
}

void AWheelSpikeGameMode::Record(double DeltaSeconds, double WallFrameMs, const FVector& Push)
{
	if (Rows.IsEmpty())
	{
		FString Header = TEXT("frame,t_s,dt_s,x_cm,y_cm,z_cm,pitch_deg,yaw_deg,roll_deg,vx_cmps,vy_cmps,vz_cmps,wz_degps,"
			"forward_cmps,lateral_cmps,push,solve_passes,solve_converged,solve_change_cmps,wall_frame_ms,tilt_deg,wx_degps,wy_degps,"
			"body_hits,wheel_fx,wheel_fy,wheel_fz,wheel_tx,wheel_ty,wheel_tz");
		for (int32 Index = 0; Index < Rig->NumWheels(); ++Index)
		{
			Header += FString::Printf(TEXT(",w%d_hit,w%d_comp_cm,w%d_fz,w%d_flong,w%d_flat,w%d_limit,w%d_spin_radps,w%d_target_radps,"
				"w%d_motor,w%d_brake,w%d_vlong_cmps,w%d_vlat_cmps,w%d_slip_cmps,w%d_saturated,w%d_known_dv_long,w%d_known_dv_lat,"
				"w%d_gravity_dv_long,w%d_end_slip_cmps,w%d_end_vlat_cmps,w%d_start_pen,w%d_friction_power,w%d_wheel_power"),
				Index, Index, Index, Index, Index, Index, Index, Index, Index, Index, Index, Index, Index, Index, Index, Index, Index,
				Index, Index, Index, Index, Index);
		}
		Rows.Add(Header);
	}

	const UStaticMeshComponent* Body = Rig->GetBody();
	const FVector P = Body->GetComponentLocation();
	const FRotator R = Body->GetComponentRotation();
	const FVector V = Body->GetPhysicsLinearVelocity();
	const FVector W = Body->GetPhysicsAngularVelocityInDegrees();
	const FSolveStats& Stats = Rig->GetSolveStats();
	const double TiltDeg = FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(Body->GetUpVector().Z, -1.0, 1.0)));
	const FVector WheelForce = Rig->GetWheelForce();
	const FVector WheelTorque = Rig->GetWheelTorque();
	FString Row = FString::Printf(TEXT("%lld,%.6f,%.6f,%.4f,%.4f,%.4f,%.5f,%.5f,%.5f,%.4f,%.4f,%.4f,%.5f,%.4f,%.4f,%.2f,%d,%d,%.3e,%.3f,"
		"%.5f,%.5f,%.5f,%d,%.3f,%.3f,%.3f,%.1f,%.1f,%.1f"),
		Frame, SimTimeS, DeltaSeconds, P.X, P.Y, P.Z, R.Pitch, R.Yaw, R.Roll, V.X, V.Y, V.Z, W.Z,
		FVector::DotProduct(V, Body->GetForwardVector()), FVector::DotProduct(V, Body->GetRightVector()), Push.Size(),
		Stats.Iterations, Stats.bConverged ? 1 : 0, Stats.LastChangeCmps, WallFrameMs, TiltDeg, W.X, W.Y, Rig->GetBodyHits(),
		WheelForce.X, WheelForce.Y, WheelForce.Z, WheelTorque.X, WheelTorque.Y, WheelTorque.Z);
	for (const AWheelRig::FWheelRecord& Wheel : Rig->GetRecords())
	{
		const FWheelResult& Result = Wheel.Result;
		Row += FString::Printf(TEXT(",%d,%.4f,%.3f,%.3f,%.3f,%.3f,%.5f,%.5f,%.2f,%.2f,%.4f,%.4f,%.4f,%d,%.6f,%.6f,%.6f,%.6f,%.6f,%d,%.6e,%.6e"),
			Wheel.Contact.bHit ? 1 : 0, Wheel.Contact.CompressionCm, Result.NormalForce, Result.LongForce, Result.LatForce,
			Result.FrictionLimit, Wheel.SpinRadps, Wheel.TargetSpinRadps, Result.MotorTorque, Result.BrakeTorque, Result.LongVelocity,
			Result.LatVelocity, Result.SlipCmps, Result.bSaturated ? 1 : 0, Result.KnownDvLong, Result.KnownDvLat, Result.GravityDvLong,
			Result.EndSlipCmps, Result.EndLatVelocity, Wheel.bStartPenetrating ? 1 : 0, Result.FrictionPower, Result.WheelPower);
	}
	Rows.Add(MoveTemp(Row));
}

void AWheelSpikeGameMode::Finish(const FString& Outcome)
{
	bFinished = true;
	const FString Base = OutDir / Scenario;
	if (!Rows.IsEmpty())
	{
		FFileHelper::SaveStringArrayToFile(Rows, *(Base + TEXT(".csv")));
	}
	const RoverloomWheel::FWheelParams Params = Rig ? Rig->GetParams() : RoverloomWheel::FWheelParams();
	const FBodyInstance* Instance = Rig ? Rig->GetBody()->GetBodyInstance() : nullptr;
	const bool bBody = Instance && Instance->IsValidBodyInstance();
	const double Mass = bBody ? Instance->GetBodyMass() : 0.0;
	const FVector Inertia = bBody ? Instance->GetBodyInertiaTensor() : FVector::ZeroVector;
	const FBodyState State = Rig ? Rig->GetLastBodyState() : FBodyState();
	const FVector* Inv = State.InvInertia;
	const FString Meta = FString::Printf(
		TEXT("{\n  \"experiment\": \"unreal_wheel_model\",\n  \"solver\": \"coupled_pgs_slip_friction\",\n  \"not_for_scoring\": true,\n  \"outcome\": \"%s\",\n"
			 "  \"scenario\": \"%s\",\n  \"wheels\": %d,\n  \"pair\": %s,\n  \"sweep\": %s,\n  \"friction\": %.3f,\n  \"slope_deg\": %.3f,\n"
			 "  \"step_cm\": %.1f,\n  \"spring_rate\": %.3f,\n  \"damper_rate\": %.3f,\n  \"motor_max_torque\": %.1f,\n"
			 "  \"brake_max_torque\": %.1f,\n  \"mass_kg\": %.3f,\n  \"principal_inertia\": [%.1f, %.1f, %.1f],\n"
			 "  \"inv_inertia_rows\": [[%.6e, %.6e, %.6e], [%.6e, %.6e, %.6e], [%.6e, %.6e, %.6e]],\n  \"body_hits\": %d,\n"
			 "  \"frames\": %lld,\n  \"sim_time_s\": %.6f,\n  \"fixed_time_step\": %s,\n  \"fixed_delta_s\": %.6f,\n"
			 "  \"gravity_z\": %.3f,\n  \"engine\": \"%s\"\n}\n"),
		*Outcome, *Scenario, Rig ? Rig->NumWheels() : 0, bPair ? TEXT("true") : TEXT("false"), bSweep ? TEXT("true") : TEXT("false"),
		Friction, SlopeDeg, StepCm, Params.SpringRate, Params.DamperRate, Params.MotorMaxTorque, Params.BrakeMaxTorque, Mass,
		Inertia.X, Inertia.Y, Inertia.Z, Inv[0].X, Inv[0].Y, Inv[0].Z, Inv[1].X, Inv[1].Y, Inv[1].Z, Inv[2].X, Inv[2].Y, Inv[2].Z,
		Rig ? Rig->GetBodyHits() : 0, Frame, SimTimeS, FApp::UseFixedTimeStep() ? TEXT("true") : TEXT("false"),
		FApp::GetFixedDeltaTime(), GetWorld()->GetGravityZ(), *FEngineVersion::Current().ToString());
	FFileHelper::SaveStringToFile(Meta, *(Base + TEXT(".json")));
	UE_LOG(LogRoverloom, Display, TEXT("Wheel scenario %s finished: %s, %lld frames"), *Scenario, *Outcome, Frame);
	FPlatformMisc::RequestExit(false, TEXT("RoverloomWheelSpike"));
}
