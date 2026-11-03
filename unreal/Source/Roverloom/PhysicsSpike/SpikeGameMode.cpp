#include "SpikeGameMode.h"

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
#include "SpikeRover.h"

using namespace RoverloomSpike;

namespace
{
	const double SettleS = 3.0;

	FString JsonEscape(const FString& Text)
	{
		return Text.Replace(TEXT("\\"), TEXT("\\\\")).Replace(TEXT("\""), TEXT("\\\""));
	}
}

ASpikeGameMode::ASpikeGameMode()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = true;
	PrimaryActorTick.TickGroup = TG_PrePhysics;
	DefaultPawnClass = nullptr;
}

void ASpikeGameMode::StartPlay()
{
	Super::StartPlay();

	const TCHAR* CommandLine = FCommandLine::Get();
	FParse::Value(CommandLine, TEXT("SpikeScenario="), Scenario);
	FParse::Value(CommandLine, TEXT("SpikeSlopeDeg="), SlopeDeg);
	FParse::Value(CommandLine, TEXT("SpikeObstacleCm="), ObstacleCm);
	FParse::Value(CommandLine, TEXT("SpikeSeed="), Seed);
	if (!FParse::Value(CommandLine, TEXT("SpikeOut="), OutDir))
	{
		OutDir = FPaths::ProjectSavedDir() / TEXT("PhysicsSpike") / TEXT("manual");
	}
	Random.Initialize(Seed);

	UWorld* World = GetWorld();
	AWorldSettings* Settings = World->GetWorldSettings();
	Settings->bGlobalGravitySet = true;
	Settings->GlobalGravityZ = MarsGravityZ;

	Material = NewObject<UPhysicalMaterial>(this);
	Material->Friction = Friction;
	Material->StaticFriction = Friction;
	Material->Restitution = 0.0f;

	FVector RoverLocation(0.0, 0.0, 0.5);
	FRotator RoverRotation = FRotator::ZeroRotator;
	bool bPin = false;

	if (Scenario == TEXT("slope"))
	{
		const FRotator Tilt(SlopeDeg, 0.0, 0.0);
		const FVector Up = Tilt.RotateVector(FVector::UpVector);
		SpawnBlock(-50.0 * Up, Tilt, FVector(20000.0, 4000.0, 100.0));
		RoverLocation = 0.5 * Up;
		RoverRotation = Tilt;
		DurationS = 30.0;
	}
	else
	{
		SpawnBlock(FVector(0.0, 0.0, -50.0), FRotator::ZeroRotator, FVector(20000.0, 20000.0, 100.0));
		if (Scenario == TEXT("probe"))
		{
			RoverLocation.Z = 300.0;
			bPin = true;
			DurationS = 7.0;
		}
		else if (Scenario == TEXT("freefall"))
		{
			RoverLocation.Z = 500.0;
			DurationS = 1.5;
		}
		else if (Scenario == TEXT("static"))
		{
			DurationS = 15.0;
		}
		else if (Scenario == TEXT("straight") || Scenario == TEXT("turn"))
		{
			DurationS = SettleS + 20.0;
		}
		else if (Scenario == TEXT("perf"))
		{
			DurationS = SettleS + 60.0;
		}
		else if (Scenario == TEXT("obstacle"))
		{
			SpawnBlock(FVector(800.0, 0.0, ObstacleCm / 2.0), FRotator::ZeroRotator, FVector(1000.0, 800.0, ObstacleCm));
			DurationS = SettleS + 40.0;
		}
		else if (Scenario == TEXT("stability"))
		{
			FRandomStream Layout(Seed + 1);
			for (int32 Index = 0; Index < 30; ++Index)
			{
				const FVector Center(Layout.FRandRange(-1500.0, 1500.0), Layout.FRandRange(-1500.0, 1500.0), 5.0);
				if (Center.Size2D() > 400.0)
				{
					SpawnBlock(Center, FRotator(0.0, Layout.FRandRange(0.0, 90.0), 0.0), FVector(100.0, 100.0, 10.0));
				}
			}
			DurationS = 600.0;
		}
		else
		{
			UE_LOG(LogRoverloom, Error, TEXT("Unknown spike scenario '%s'"), *Scenario);
			Finish(TEXT("unknown_scenario"));
			return;
		}
	}

	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	Rover = World->SpawnActor<ASpikeRover>(ASpikeRover::StaticClass(), RoverLocation, RoverRotation, Params);
	Rover->Build(Material, bPin);

	ADirectionalLight* Sun = World->SpawnActor<ADirectionalLight>(FVector::ZeroVector, FRotator(-40.0, 30.0, 0.0));
	(void)Sun;

	StartWallS = FPlatformTime::Seconds();
	LastWallS = StartWallS;
	UE_LOG(LogRoverloom, Display, TEXT("Spike scenario %s started, gravity %.3f, %s"), *Scenario, World->GetGravityZ(),
		*Rover->DescribeCollision());
}

void ASpikeGameMode::SpawnBlock(const FVector& Center, const FRotator& Rotation, const FVector& SizeCm)
{
	UWorld* World = GetWorld();
	AStaticMeshActor* Block = World->SpawnActorDeferred<AStaticMeshActor>(AStaticMeshActor::StaticClass(),
		FTransform(Rotation, Center, SizeCm / 100.0), nullptr, nullptr, ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
	UStaticMeshComponent* Mesh = Block->GetStaticMeshComponent();
	Mesh->SetMobility(EComponentMobility::Movable);
	Mesh->SetStaticMesh(LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")));
	Mesh->SetPhysMaterialOverride(Material);
	Block->FinishSpawning(FTransform(Rotation, Center, SizeCm / 100.0));
}

void ASpikeGameMode::CommandAt(double TimeS, double& OutForwardCmps, double& OutYawRateDegps)
{
	OutForwardCmps = 0.0;
	OutYawRateDegps = 0.0;
	if (Scenario == TEXT("probe"))
	{
		OutForwardCmps = TimeS < 1.0 ? 0.0 : (TimeS < 4.0 ? MaxSpeedCmps : -MaxSpeedCmps);
	}
	else if (Scenario == TEXT("straight") || Scenario == TEXT("perf") || Scenario == TEXT("obstacle"))
	{
		OutForwardCmps = TimeS < SettleS ? 0.0 : MaxSpeedCmps;
	}
	else if (Scenario == TEXT("turn"))
	{
		OutYawRateDegps = TimeS < SettleS ? 0.0 : MaxYawRateDegps;
	}
	else if (Scenario == TEXT("slope"))
	{
		OutForwardCmps = TimeS < 10.0 ? 0.0 : MaxSpeedCmps;
	}
	else if (Scenario == TEXT("stability") && TimeS >= SettleS)
	{
		if (TimeS >= NextRandomChangeS)
		{
			RandomForwardCmps = Random.FRandRange(-MaxSpeedCmps, MaxSpeedCmps);
			RandomYawRateDegps = Random.FRandRange(-MaxYawRateDegps, MaxYawRateDegps);
			NextRandomChangeS = TimeS + 5.0;
		}
		OutForwardCmps = RandomForwardCmps;
		OutYawRateDegps = RandomYawRateDegps;
	}
}

void ASpikeGameMode::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (bFinished || !Rover)
	{
		return;
	}
	if (!bConnectAttempted)
	{
		// Time starts on the frame the joints exist. Nothing simulates before then.
		if (!Rover->TryConnect())
		{
			return;
		}
		bConnectAttempted = true;
		if (!Rover->IsConnected())
		{
			Finish(TEXT("joints_not_created"));
			return;
		}
		LastWallS = FPlatformTime::Seconds();
	}

	if (!bViewSet)
	{
		if (APlayerController* Controller = GetWorld()->GetFirstPlayerController())
		{
			ACameraActor* Camera = GetWorld()->SpawnActor<ACameraActor>(FVector(-1200.0, -900.0, 600.0), FRotator(-20.0, 37.0, 0.0));
			Controller->SetViewTarget(Camera);
			bViewSet = true;
		}
	}

	const double NowWallS = FPlatformTime::Seconds();
	const double WallFrameMs = 1000.0 * (NowWallS - LastWallS);
	LastWallS = NowWallS;

	// Frame 0 is the state before the first physics step. Each later row is the state after the previous step.
	if (Frame > 0)
	{
		SimTimeS += DeltaSeconds;
	}

	double ForwardCmps = 0.0;
	double YawRateDegps = 0.0;
	CommandAt(SimTimeS, ForwardCmps, YawRateDegps);
	Record(DeltaSeconds, WallFrameMs, ForwardCmps, YawRateDegps);
	Rover->SetCommand(ForwardCmps, YawRateDegps);
	++Frame;

	if (Rover->GetChassis()->GetComponentLocation().ContainsNaN())
	{
		Finish(TEXT("nan"));
	}
	else if (SimTimeS >= DurationS)
	{
		Finish(TEXT("completed"));
	}
}

void ASpikeGameMode::Record(double DeltaSeconds, double WallFrameMs, double ForwardCmps, double YawRateDegps)
{
	if (Rows.IsEmpty())
	{
		FString Header = TEXT("frame,t_s,dt_s,wall_frame_ms,cmd_forward_cmps,cmd_yaw_rate_degps,x_cm,y_cm,z_cm,pitch_deg,yaw_deg,roll_deg,"
			"vx_cmps,vy_cmps,vz_cmps,wx_degps,wy_degps,wz_degps,forward_cmps,axle_fx,axle_fy,axle_fz");
		for (int32 Index = 0; Index < NumWheels; ++Index)
		{
			Header += FString::Printf(TEXT(",w%d_spin_radps,w%d_target_radps,w%d_x_cm,w%d_z_cm"), Index, Index, Index, Index);
		}
		Rows.Add(Header);
	}

	const UStaticMeshComponent* Chassis = Rover->GetChassis();
	const FVector P = Chassis->GetComponentLocation();
	const FRotator R = Chassis->GetComponentRotation();
	const FVector V = Chassis->GetPhysicsLinearVelocity();
	const FVector W = Chassis->GetPhysicsAngularVelocityInDegrees();
	const FVector F = Rover->GetAxleForceSum();
	FString Row = FString::Printf(TEXT("%lld,%.6f,%.6f,%.3f,%.4f,%.4f,%.4f,%.4f,%.4f,%.5f,%.5f,%.5f,%.4f,%.4f,%.4f,%.5f,%.5f,%.5f,%.4f,%.2f,%.2f,%.2f"),
		Frame, SimTimeS, DeltaSeconds, WallFrameMs, ForwardCmps, YawRateDegps, P.X, P.Y, P.Z, R.Pitch, R.Yaw, R.Roll, V.X, V.Y, V.Z,
		W.X, W.Y, W.Z, FVector::DotProduct(V, Chassis->GetForwardVector()), F.X, F.Y, F.Z);
	for (int32 Index = 0; Index < NumWheels; ++Index)
	{
		const FVector Wheel = Rover->GetWheelLocation(Index);
		Row += FString::Printf(TEXT(",%.5f,%.5f,%.4f,%.4f"), Rover->GetWheelSpinRadps(Index), Rover->GetWheelTargetRadps(Index), Wheel.X, Wheel.Z);
	}
	Rows.Add(MoveTemp(Row));
}

void ASpikeGameMode::Finish(const FString& Outcome)
{
	bFinished = true;
	const FString Base = OutDir / Scenario;
	if (!Rows.IsEmpty())
	{
		FFileHelper::SaveStringArrayToFile(Rows, *(Base + TEXT(".csv")));
	}

	const FString Meta = FString::Printf(
		TEXT("{\n  \"experiment\": \"unreal_physics_spike_r0\",\n  \"not_for_scoring\": true,\n  \"outcome\": \"%s\",\n"
			 "  \"scenario\": \"%s\",\n  \"slope_deg\": %.3f,\n  \"obstacle_cm\": %.3f,\n  \"seed\": %d,\n  \"duration_s\": %.3f,\n"
			 "  \"frames\": %lld,\n  \"sim_time_s\": %.6f,\n  \"wall_time_s\": %.3f,\n  \"fixed_time_step\": %s,\n"
			 "  \"fixed_delta_s\": %.6f,\n  \"gravity_z\": %.3f,\n  \"engine\": \"%s\",\n  \"collision\": \"%s\",\n"
			 "  \"command_line\": \"%s\"\n}\n"),
		*Outcome, *Scenario, SlopeDeg, ObstacleCm, Seed, DurationS, Frame, SimTimeS, FPlatformTime::Seconds() - StartWallS,
		FApp::UseFixedTimeStep() ? TEXT("true") : TEXT("false"), FApp::GetFixedDeltaTime(), GetWorld()->GetGravityZ(),
		*FEngineVersion::Current().ToString(), Rover ? *JsonEscape(Rover->DescribeCollision()) : TEXT(""),
		*JsonEscape(FCommandLine::Get()));
	FFileHelper::SaveStringToFile(Meta, *(Base + TEXT(".json")));

	UE_LOG(LogRoverloom, Display, TEXT("Spike scenario %s finished: %s, %lld frames"), *Scenario, *Outcome, Frame);
	FPlatformMisc::RequestExit(false, TEXT("RoverloomSpike"));
}
