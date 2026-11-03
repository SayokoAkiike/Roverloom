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
		bool bPair;
		bool bSweep;
		double Friction;
		double SlopeDeg;
		double DurationS;
	};
	static const FPlan Plans[] = {
		{TEXT("a1"), false, false, 0.6, 0.0, 6.0},
		{TEXT("a1s"), false, true, 0.6, 0.0, 6.0},
		{TEXT("a2"), false, false, 0.6, 0.0, 12.0},
		{TEXT("a2s"), false, true, 0.6, 0.0, 12.0},
		{TEXT("a3"), false, false, 0.05, 0.0, 8.0},
		{TEXT("a4"), false, false, 0.1, 0.0, 11.0},
		{TEXT("a5"), false, false, 0.3, 0.0, 6.0},
		{TEXT("a6"), false, false, 0.6, 10.0, 6.0},
		{TEXT("a7"), false, false, 0.1, 10.0, 6.0},
		{TEXT("b1"), true, false, 0.6, 0.0, 12.0},
		{TEXT("b2"), true, false, 0.6, 0.0, 10.0},
		{TEXT("b3"), true, false, 0.6, 0.0, 11.0},
		{TEXT("b4"), true, false, 0.6, 10.0, 6.0},
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
	bPair = Plan->bPair;
	bSweep = Plan->bSweep;
	Friction = Plan->Friction;
	SlopeDeg = Plan->SlopeDeg;
	DurationS = Plan->DurationS;

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

	FActorSpawnParameters SpawnParams;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	Rig = World->SpawnActor<AWheelRig>(AWheelRig::StaticClass(), RideHeightCm * Up, Tilt, SpawnParams);
	TArray<AWheelRig::FWheelSetup> Wheels;
	if (bPair)
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

void AWheelSpikeGameMode::Command(double TimeS, TArray<double>& OutTargets, EWheelMode& OutMode, FVector& OutPush) const
{
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
		if (APlayerController* Controller = GetWorld()->GetFirstPlayerController())
		{
			Controller->SetViewTarget(GetWorld()->SpawnActor<ACameraActor>(FVector(-600.0, -450.0, 300.0), FRotator(-20.0, 37.0, 0.0)));
		}
	}
	if (Frame > 0)
	{
		SimTimeS += DeltaSeconds;
	}

	TArray<double> Targets;
	EWheelMode Mode = EWheelMode::Drive;
	FVector Push = FVector::ZeroVector;
	Command(SimTimeS, Targets, Mode, Push);
	Rig->SetTargets(Targets, Mode);
	Rig->StepWheels(DeltaSeconds);
	if (!Push.IsZero())
	{
		Rig->GetBody()->AddForce(Push);
	}
	Record(DeltaSeconds, Push);
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

void AWheelSpikeGameMode::Record(double DeltaSeconds, const FVector& Push)
{
	if (Rows.IsEmpty())
	{
		FString Header = TEXT("frame,t_s,dt_s,x_cm,y_cm,z_cm,pitch_deg,yaw_deg,roll_deg,vx_cmps,vy_cmps,vz_cmps,wz_degps,"
			"forward_cmps,lateral_cmps,push");
		for (int32 Index = 0; Index < Rig->NumWheels(); ++Index)
		{
			Header += FString::Printf(TEXT(",w%d_hit,w%d_comp_cm,w%d_fz,w%d_flong,w%d_flat,w%d_limit,w%d_spin_radps,w%d_target_radps,"
				"w%d_motor,w%d_brake,w%d_vlong_cmps,w%d_vlat_cmps,w%d_slip_cmps,w%d_saturated"),
				Index, Index, Index, Index, Index, Index, Index, Index, Index, Index, Index, Index, Index, Index);
		}
		Rows.Add(Header);
	}

	const UStaticMeshComponent* Body = Rig->GetBody();
	const FVector P = Body->GetComponentLocation();
	const FRotator R = Body->GetComponentRotation();
	const FVector V = Body->GetPhysicsLinearVelocity();
	const FVector W = Body->GetPhysicsAngularVelocityInDegrees();
	FString Row = FString::Printf(TEXT("%lld,%.6f,%.6f,%.4f,%.4f,%.4f,%.5f,%.5f,%.5f,%.4f,%.4f,%.4f,%.5f,%.4f,%.4f,%.2f"),
		Frame, SimTimeS, DeltaSeconds, P.X, P.Y, P.Z, R.Pitch, R.Yaw, R.Roll, V.X, V.Y, V.Z, W.Z,
		FVector::DotProduct(V, Body->GetForwardVector()), FVector::DotProduct(V, Body->GetRightVector()), Push.Size());
	for (const AWheelRig::FWheelRecord& Wheel : Rig->GetRecords())
	{
		const FWheelResult& Result = Wheel.Result;
		Row += FString::Printf(TEXT(",%d,%.4f,%.3f,%.3f,%.3f,%.3f,%.5f,%.5f,%.2f,%.2f,%.4f,%.4f,%.4f,%d"), Wheel.Contact.bHit ? 1 : 0,
			Wheel.Contact.CompressionCm, Result.NormalForce, Result.LongForce, Result.LatForce, Result.FrictionLimit, Wheel.SpinRadps,
			Wheel.TargetSpinRadps, Result.MotorTorque, Result.BrakeTorque, Result.LongVelocity, Result.LatVelocity, Result.SlipCmps,
			Result.bSaturated ? 1 : 0);
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
	const FString Meta = FString::Printf(
		TEXT("{\n  \"experiment\": \"unreal_wheel_model\",\n  \"not_for_scoring\": true,\n  \"outcome\": \"%s\",\n"
			 "  \"scenario\": \"%s\",\n  \"pair\": %s,\n  \"sweep\": %s,\n  \"friction\": %.3f,\n  \"slope_deg\": %.3f,\n"
			 "  \"spring_rate\": %.3f,\n  \"damper_rate\": %.3f,\n  \"motor_max_torque\": %.1f,\n  \"brake_max_torque\": %.1f,\n"
			 "  \"frames\": %lld,\n  \"sim_time_s\": %.6f,\n  \"fixed_time_step\": %s,\n  \"fixed_delta_s\": %.6f,\n"
			 "  \"gravity_z\": %.3f,\n  \"engine\": \"%s\"\n}\n"),
		*Outcome, *Scenario, bPair ? TEXT("true") : TEXT("false"), bSweep ? TEXT("true") : TEXT("false"), Friction, SlopeDeg,
		Params.SpringRate, Params.DamperRate, Params.MotorMaxTorque, Params.BrakeMaxTorque, Frame, SimTimeS,
		FApp::UseFixedTimeStep() ? TEXT("true") : TEXT("false"), FApp::GetFixedDeltaTime(), GetWorld()->GetGravityZ(),
		*FEngineVersion::Current().ToString());
	FFileHelper::SaveStringToFile(Meta, *(Base + TEXT(".json")));
	UE_LOG(LogRoverloom, Display, TEXT("Wheel scenario %s finished: %s, %lld frames"), *Scenario, *Outcome, Frame);
	FPlatformMisc::RequestExit(false, TEXT("RoverloomWheelSpike"));
}
