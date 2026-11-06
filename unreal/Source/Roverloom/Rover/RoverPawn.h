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
};
