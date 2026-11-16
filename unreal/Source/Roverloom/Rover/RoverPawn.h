#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"

#include "CommandRouter.h"

#include "RoverPawn.generated.h"

class ACameraActor;
class AWheelRig;
class UCameraComponent;
class UInputAction;
class UInputMappingContext;
class UPhysicalMaterial;
class USpringArmComponent;
class UStaticMeshComponent;
struct FInputActionValue;

UENUM()
enum class ERoverCamera : uint8
{
	Chase,
	Mast,
	Hazard,
	Free,
};

// What the HUD shows. Contract units: m/s and rad/s, positive yaw turning left.
struct FRoverStatus
{
	bool bReady = false;
	double ForwardMps = 0.0;
	double YawRateRadps = 0.0;
	double TiltDeg = 0.0;
	FVector SitePositionM = FVector::ZeroVector;
	RoverloomCommand::FAction Applied;
	bool bClamped = false;
	bool bWatchdogExpired = true;
	bool bHasCommanded = false;
	FString Source;
	ERoverCamera Camera = ERoverCamera::Chase;
	int32 WheelsInContact = 0;
	int32 Resets = 0;
	FString LastReset;
	double StepDtS = 0.0;
	bool bStepClamped = false;
	// The last 10 s window of frames: mean and 95th percentile frame time, and the share of frames with focus.
	double FrameMsMean = 0.0;
	double FrameMsP95 = 0.0;
	double FocusShare = 0.0;
	// G3: the Mission Core's verdict, shown as received; Unreal never judges the mission itself.
	FString MissionLine;
	bool bMissionEnded = false;
};

// The playable six-wheel rover. It drives the WheelSpike rig (drive model P, provisional) through the one command path,
// shows the rig's body with visual wheels, and carries four cameras. Visual parts have no collision, so they never
// change a physics value; the rig alone touches the ground.
UCLASS(NotBlueprintable)
class ARoverPawn : public APawn
{
	GENERATED_BODY()

public:
	ARoverPawn();

	virtual void Tick(float DeltaSeconds) override;
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;
	virtual void PawnClientRestart() override;

	const FRoverStatus& GetStatus() const { return Status; }
	static const TCHAR* CameraName(ERoverCamera Camera);
	static const TCHAR* KeyboardSource;
	static const TCHAR* AgentSource; // Actions from a Python agent over the mission link (bridge v1, real time)

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
	void SpawnRig();
	void ResetRig(const FString& Reason);
	void FollowBody();
	void UpdateWheels(double DeltaSeconds);
	void UpdateFreeCamera(double DeltaSeconds);
	void SetCamera(ERoverCamera Camera);
	void CreateInput();
	void AddMappingContext();
	void LogAndCapture(double NowS);
	void RecordFrame(double DeltaSeconds);
	void DriveScriptCommand(double NowS);
	void MissionLinkStart();
	void MissionLinkTick(double NowS);
	void MissionLinkStop();
	void MissionLinkDrop(const TCHAR* Why);
	void DriveScriptSample(double NowS, double StepDt);
	void LogRenderSettings(const TCHAR* When) const;

	void OnDrive(const FInputActionValue& Value);
	void OnDriveReleased(const FInputActionValue& Value);
	void OnTurn(const FInputActionValue& Value);
	void OnTurnReleased(const FInputActionValue& Value);
	void OnNextCamera(const FInputActionValue& Value);
	void OnReset(const FInputActionValue& Value);
	void OnLook(const FInputActionValue& Value);
	void OnFreeMove(const FInputActionValue& Value);
	void OnFreeMoveReleased(const FInputActionValue& Value);
	void OnFreeLift(const FInputActionValue& Value);
	void OnFreeLiftReleased(const FInputActionValue& Value);

	UPROPERTY()
	TObjectPtr<USceneComponent> Root;
	UPROPERTY()
	TObjectPtr<USpringArmComponent> ChaseArm;
	UPROPERTY()
	TObjectPtr<UCameraComponent> ChaseCamera;
	UPROPERTY()
	TObjectPtr<UCameraComponent> MastCamera;
	UPROPERTY()
	TObjectPtr<UCameraComponent> HazardCamera;
	UPROPERTY()
	TArray<TObjectPtr<UStaticMeshComponent>> Wheels;
	UPROPERTY()
	TArray<TObjectPtr<UStaticMeshComponent>> WheelMarks;
	UPROPERTY()
	TArray<TObjectPtr<UStaticMeshComponent>> Legs;
	UPROPERTY()
	TArray<TObjectPtr<UStaticMeshComponent>> Parts; // Rockers, mast, mast head, panel
	// V2 visual model (scripts/blender/build_rover.py), used when its meshes exist under /Game/Rover. Visual only.
	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> ModelBody;
	UPROPERTY()
	TArray<TObjectPtr<UStaticMeshComponent>> ModelAxles;
	bool bModelV2 = false;
	bool ApplyModelV2();

	UPROPERTY()
	TObjectPtr<AWheelRig> Rig;
	UPROPERTY()
	TObjectPtr<UPhysicalMaterial> RigMaterial;
	UPROPERTY()
	TObjectPtr<ACameraActor> FreeCamera;

	UPROPERTY()
	TObjectPtr<UInputMappingContext> Mapping;
	UPROPERTY()
	TObjectPtr<UInputAction> DriveAction;
	UPROPERTY()
	TObjectPtr<UInputAction> TurnAction;
	UPROPERTY()
	TObjectPtr<UInputAction> CameraAction;
	UPROPERTY()
	TObjectPtr<UInputAction> ResetAction;
	UPROPERTY()
	TObjectPtr<UInputAction> LookAction;
	UPROPERTY()
	TObjectPtr<UInputAction> FreeMoveAction;
	UPROPERTY()
	TObjectPtr<UInputAction> FreeLiftAction;

	TUniquePtr<RoverloomCommand::FCommandRouter> Router;
	FTransform StartTransform;
	bool bRigReady = false;
	double DriveInput = 0.0; // -1..1, W positive
	double TurnInput = 0.0;  // -1..1, A positive (left, as the contract)
	bool bKeyboardHeld = false;
	FVector2D FreeMove = FVector2D::ZeroVector;
	double FreeLift = 0.0;
	TArray<double> WheelAnglesRad;
	ERoverCamera Camera = ERoverCamera::Chase;
	FRoverStatus Status;
	// Start-up checks: one status line 3 s after the rig is ready, and with -RoverShotDir=<dir> one screenshot per
	// rover camera, which switches cameras by itself once and then returns to the chase camera.
	double ReadyTimeS = -1.0;
	bool bLoggedSettle = false;
	FString ShotDir;
	int32 ShotStep = 0;
	// Frame timing over 10 s windows, logged for performance checks.
	TArray<double> FrameMs;
	double GameMsSum = 0.0;
	double RenderMsSum = 0.0;
	double GpuMsSum = 0.0;
	int32 FocusFrames = 0;
	double WindowStartS = -1.0;
	// -RoverBench=<seconds>: a benchmark run. No camera tour; at the end, one chase screenshot if -RoverShotDir is set,
	// the effective render settings logged again, and the game exits.
	double BenchSeconds = 0.0;
	double BenchShotS = -1.0;
	bool bBenchProfiled = false;
	// -RoverDrive=<preset>: a fixed drive script for measuring drive model P, sent through the same command path as the
	// keyboard. Each phase logs commanded and measured values; nothing in the model changes.
	struct FDrivePhase
	{
		FString Name;
		double Seconds = 0.0;
		double LinearMps = 0.0;
		double YawRadps = 0.0;
	};
	TArray<FDrivePhase> DrivePhases;
	// G3 mission link: a loopback listener on 127.0.0.1:8100 (the night tunnel's port). Sends telemetry at 10 Hz and
	// shows the Mission Core's mission_state lines. JSON Lines as in the bridge protocol, 1 MiB per line.
	class FSocket* LinkListen = nullptr;
	class FSocket* LinkClient = nullptr;
	FString LinkBuffer;
	double LinkLastSendS = -1.0;
	FString LinkLastLogged;
	// G4a: keys-g3 presses W through Enhanced Input (as a key would) from KeySimStartS for KeySimSeconds after the rig
	// is ready; the drive script is not used. The first mission verdict is captured as Mission.png.
	double KeySimStartS = -1.0;
	double KeySimSeconds = 0.0;
	bool bKeySimLogged = false;
	bool bMissionShotTaken = false;
	int32 DriveIndex = -1;
	double DrivePhaseStartS = 0.0;
	FVector DriveStartCm = FVector::ZeroVector;
	FVector DriveStartForward = FVector::ForwardVector;
	double DriveTimeS = 0.0;
	double DriveDistanceAlongM = 0.0;
	double DriveHeadingRad = 0.0;
	double DriveMaxTiltDeg = 0.0;
	int32 DriveMinWheels = 6;
	int32 DriveStartResets = 0;
	int32 DriveClampedFrames = 0;
	int32 DriveFrames = 0;
	// Diagnostics: wheel spin against target, and the left-right spin difference against its target.
	double DriveSpinRatioSum = 0.0;
	int32 DriveSpinSamples = 0;
	double DriveDiffRatioSum = 0.0;
	int32 DriveDiffSamples = 0;
};
