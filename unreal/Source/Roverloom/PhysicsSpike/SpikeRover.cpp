#include "SpikeRover.h"

#include "Components/StaticMeshComponent.h"
#include "Engine/CollisionProfile.h"
#include "Engine/StaticMesh.h"
#include "PhysicalMaterials/PhysicalMaterial.h"
#include "PhysicsEngine/BodySetup.h"
#include "PhysicsEngine/PhysicsConstraintComponent.h"

#include "../Roverloom.h"

using namespace RoverloomSpike;

namespace
{
	const TCHAR* CubePath = TEXT("/Engine/BasicShapes/Cube.Cube");
	const TCHAR* SpherePath = TEXT("/Engine/BasicShapes/Sphere.Sphere");

	// Engine basic shapes are 100 cm across.
	UStaticMeshComponent* MakeBody(AActor* Owner, FName Name, const TCHAR* MeshPath, const FTransform& World, double MassKg,
		UPhysicalMaterial* Material)
	{
		UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, MeshPath);
		check(Mesh);
		UStaticMeshComponent* Body = NewObject<UStaticMeshComponent>(Owner, Name);
		Body->SetupAttachment(Owner->GetRootComponent());
		Body->SetMobility(EComponentMobility::Movable);
		Body->SetStaticMesh(Mesh);
		Body->SetCollisionProfileName(UCollisionProfile::PhysicsActor_ProfileName);
		Body->RegisterComponent();
		Body->SetWorldTransform(World, false, nullptr, ETeleportType::TeleportPhysics);
		Body->SetPhysMaterialOverride(Material);
		Body->SetLinearDamping(0.0f);
		Body->SetAngularDamping(0.0f);
		Body->SetMassOverrideInKg(NAME_None, MassKg, true);
		return Body;
	}

	FString DescribeMesh(UStaticMeshComponent* Body)
	{
		const UBodySetup* Setup = Body->GetBodySetup();
		if (!Setup)
		{
			return TEXT("no body setup");
		}
		return FString::Printf(TEXT("spheres=%d boxes=%d capsules=%d convex=%d trace_flag=%d"), Setup->AggGeom.SphereElems.Num(),
			Setup->AggGeom.BoxElems.Num(), Setup->AggGeom.SphylElems.Num(), Setup->AggGeom.ConvexElems.Num(),
			static_cast<int32>(Setup->CollisionTraceFlag));
	}
}

ASpikeRover::ASpikeRover()
{
	PrimaryActorTick.bCanEverTick = false;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	RootComponent->SetMobility(EComponentMobility::Movable);
}

void ASpikeRover::Build(UPhysicalMaterial* Material, bool bPinChassis, double InDriveMaxTorque)
{
	const FTransform Origin = GetActorTransform();

	const FVector ChassisCenter(0.0, 0.0, ChassisBottomCm + ChassisHeightCm / 2.0);
	const FTransform ChassisWorld(Origin.GetRotation(), Origin.TransformPosition(ChassisCenter),
		FVector(ChassisLengthCm, ChassisWidthCm, ChassisHeightCm) / 100.0);
	Chassis = MakeBody(this, TEXT("Chassis"), CubePath, ChassisWorld, ChassisMassKg, Material);

	for (int32 Index = 0; Index < NumWheels; ++Index)
	{
		const FTransform WheelWorld(Origin.GetRotation(), Origin.TransformPosition(WheelCenter(Index)),
			FVector(2.0 * WheelRadiusCm / 100.0));
		Wheels.Add(MakeBody(this, *FString::Printf(TEXT("Wheel%d"), Index), SpherePath, WheelWorld, WheelMassKg, Material));
	}
	bPinned = bPinChassis;
	DriveTorqueLimit = InDriveMaxTorque;
}

bool ASpikeRover::TryConnect()
{
	// Bodies are created after registration, so joints can only be made once they exist.
	if (!Chassis->GetBodyInstance()->IsValidBodyInstance())
	{
		return false;
	}
	for (UStaticMeshComponent* Wheel : Wheels)
	{
		if (!Wheel->GetBodyInstance()->IsValidBodyInstance())
		{
			return false;
		}
	}

	Chassis->SetSimulatePhysics(!bPinned);
	for (UStaticMeshComponent* Wheel : Wheels)
	{
		Wheel->SetSimulatePhysics(true);
	}

	// The joint's X axis, which is the twist axis, points along the chassis's right axis.
	const FQuat AxleRotation = GetActorQuat() * FRotator(0.0, 90.0, 0.0).Quaternion();
	for (int32 Index = 0; Index < NumWheels; ++Index)
	{
		UPhysicsConstraintComponent* Axle = NewObject<UPhysicsConstraintComponent>(this, *FString::Printf(TEXT("Axle%d"), Index));
		Axle->SetupAttachment(Chassis);
		Axle->RegisterComponent();
		Axle->SetWorldLocationAndRotation(Wheels[Index]->GetComponentLocation(), AxleRotation);
		Axle->SetDisableCollision(true);
		Axle->SetLinearXLimit(LCM_Locked, 0.0f);
		Axle->SetLinearYLimit(LCM_Locked, 0.0f);
		Axle->SetLinearZLimit(LCM_Locked, 0.0f);
		Axle->SetAngularSwing1Limit(ACM_Locked, 0.0f);
		Axle->SetAngularSwing2Limit(ACM_Locked, 0.0f);
		Axle->SetAngularTwistLimit(ACM_Free, 0.0f);
		Axle->SetAngularDriveMode(EAngularDriveMode::TwistAndSwing);
		Axle->SetAngularDriveAccelerationMode(false);
		Axle->SetAngularVelocityDriveTwistAndSwing(true, false);
		Axle->SetAngularDriveParams(0.0f, DriveDamping, DriveTorqueLimit);
		Axle->SetAngularVelocityTarget(FVector::ZeroVector);
		Axle->SetConstrainedComponents(Chassis, NAME_None, Wheels[Index], NAME_None);
		Axles.Add(Axle);
	}

	int32 Valid = 0;
	for (UPhysicsConstraintComponent* Axle : Axles)
	{
		Valid += Axle->ConstraintInstance.IsValidConstraintInstance() ? 1 : 0;
	}
	UE_LOG(LogRoverloom, Display, TEXT("Spike rover connected: %d of %d axles valid, chassis %s"), Valid, Axles.Num(),
		bPinned ? TEXT("pinned") : TEXT("simulating"));
	bConnected = Valid == NumWheels;
	return true;
}

void ASpikeRover::SetCommand(double ForwardCmps, double YawRateDegps)
{
	double LeftCmps = 0.0;
	double RightCmps = 0.0;
	SkidRimSpeeds(ForwardCmps, YawRateDegps, LeftCmps, RightCmps);
	for (int32 Index = 0; Index < Axles.Num(); ++Index)
	{
		TargetSpinRadps[Index] = RimSpeedToSpinRadps(IsLeftWheel(Index) ? LeftCmps : RightCmps);
		const double RevPerSecond = DriveTwistSign * TargetSpinRadps[Index] / (2.0 * UE_DOUBLE_PI);
		Axles[Index]->SetAngularVelocityTarget(FVector(RevPerSecond, 0.0, 0.0));
	}

	// A new drive target does not wake sleeping bodies, so keep them awake. This disables sleeping in effect.
	Chassis->WakeRigidBody();
	for (UStaticMeshComponent* Wheel : Wheels)
	{
		Wheel->WakeRigidBody();
	}
}

void ASpikeRover::SetBrake(bool bOn)
{
	if (bOn == bBraking)
	{
		return;
	}
	bBraking = bOn;
	// Braking holds zero wheel speed with no torque limit; release returns to the motor's limit.
	for (UPhysicsConstraintComponent* Axle : Axles)
	{
		Axle->SetAngularDriveParams(0.0f, DriveDamping, bOn ? 0.0f : DriveTorqueLimit);
	}
	if (bOn)
	{
		SetCommand(0.0, 0.0);
	}
}

void ASpikeRover::ApplyWheelTorque(double TorqueAboutRight)
{
	ExternalWheelTorque = TorqueAboutRight;
	for (UStaticMeshComponent* Wheel : Wheels)
	{
		Wheel->AddTorqueInRadians(Chassis->GetRightVector() * TorqueAboutRight);
	}
}

FVector ASpikeRover::GetWheelLocation(int32 Index) const
{
	return Wheels[Index]->GetComponentLocation();
}

double ASpikeRover::GetWheelSpinRadps(int32 Index) const
{
	const FVector Relative = Wheels[Index]->GetPhysicsAngularVelocityInRadians() - Chassis->GetPhysicsAngularVelocityInRadians();
	return FVector::DotProduct(Relative, Chassis->GetRightVector());
}

FVector ASpikeRover::GetAxleForceSum() const
{
	FVector Sum = FVector::ZeroVector;
	for (UPhysicsConstraintComponent* Axle : Axles)
	{
		FVector Linear;
		FVector Angular;
		Axle->GetConstraintForce(Linear, Angular);
		Sum += Linear;
	}
	return Sum;
}

FString ASpikeRover::DescribeCollision() const
{
	return FString::Printf(TEXT("chassis[%s] wheel[%s]"), *DescribeMesh(Chassis), *DescribeMesh(Wheels[0]));
}
