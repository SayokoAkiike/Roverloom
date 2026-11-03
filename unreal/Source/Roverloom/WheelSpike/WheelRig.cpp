#include "WheelRig.h"

#include "CollisionQueryParams.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/CollisionProfile.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "PhysicalMaterials/PhysicalMaterial.h"
#include "PhysicsEngine/BodyInstance.h"

using namespace RoverloomWheel;

namespace
{
	const double MarsGravity = 371.0; // cm/s^2, magnitude
	const double StaticCompressionCm = 5.0;
	const double DampingRatio = 0.7;
}

AWheelRig::AWheelRig()
{
	PrimaryActorTick.bCanEverTick = false;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	RootComponent->SetMobility(EComponentMobility::Movable);
}

void AWheelRig::Build(const FVector& SizeCm, double InMassKg, const TArray<FWheelSetup>& InWheels, bool bLockRollPitch,
	bool bLockYaw, bool bSweep, double Friction, UPhysicalMaterial* BodyMaterial)
{
	MassKg = InMassKg;
	Wheels = InWheels;
	bLockRollPitchAxes = bLockRollPitch;
	bLockYawAxis = bLockYaw;
	bUseSweep = bSweep;
	Spins.Init(0.0, Wheels.Num());
	Targets.Init(0.0, Wheels.Num());
	Records.SetNum(Wheels.Num());

	// The suspension carries an equal share of the weight at 5 cm compression.
	const double Load = MassKg * MarsGravity / Wheels.Num();
	Params.Friction = Friction;
	Params.SpringRate = SpringRateFor(Load, StaticCompressionCm);
	Params.DamperRate = DamperRateFor(Params.SpringRate, MassKg / Wheels.Num(), DampingRatio);

	Body = NewObject<UStaticMeshComponent>(this, TEXT("Body"));
	Body->SetupAttachment(RootComponent);
	Body->SetMobility(EComponentMobility::Movable);
	Body->SetStaticMesh(LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")));
	Body->SetCollisionProfileName(UCollisionProfile::PhysicsActor_ProfileName);
	Body->BodyInstance.bLockXRotation = bLockRollPitch;
	Body->BodyInstance.bLockYRotation = bLockRollPitch;
	Body->BodyInstance.bLockZRotation = bLockYaw;
	Body->BodyInstance.SetDOFLock(EDOFMode::SixDOF);
	Body->RegisterComponent();
	Body->SetWorldTransform(FTransform(GetActorQuat(), GetActorLocation(), SizeCm / 100.0), false, nullptr, ETeleportType::TeleportPhysics);
	Body->SetPhysMaterialOverride(BodyMaterial);
	Body->SetLinearDamping(0.0f);
	Body->SetAngularDamping(0.0f);
	Body->SetMassOverrideInKg(NAME_None, MassKg, true);
}

bool AWheelRig::IsReady() const
{
	if (!Body->GetBodyInstance()->IsValidBodyInstance())
	{
		return false;
	}
	if (!Body->IsSimulatingPhysics())
	{
		Body->SetSimulatePhysics(true);
	}
	return true;
}

void AWheelRig::SetTargets(const TArray<double>& TargetSpinRadps, EWheelMode InMode)
{
	Targets = TargetSpinRadps;
	Mode = InMode;
}

double AWheelRig::InverseMassAlong(const FVector& Point, const FVector& Direction) const
{
	const FBodyInstance* Instance = Body->GetBodyInstance();
	const FTransform MassFrame = Instance->GetMassSpaceToWorldSpace();
	const FVector Inertia = Instance->GetBodyInertiaTensor();
	const FVector Arm = FVector::CrossProduct(Point - MassFrame.GetLocation(), Direction);
	const FVector Local = MassFrame.InverseTransformVectorNoScale(Arm);
	FVector AngularPerTorque = MassFrame.TransformVectorNoScale(
		FVector(Local.X / Inertia.X, Local.Y / Inertia.Y, Local.Z / Inertia.Z));
	// Locked rotation axes behave as infinite inertia.
	if (bLockRollPitchAxes)
	{
		AngularPerTorque.X = 0.0;
		AngularPerTorque.Y = 0.0;
	}
	if (bLockYawAxis)
	{
		AngularPerTorque.Z = 0.0;
	}
	return 1.0 / MassKg + FVector::DotProduct(Arm, AngularPerTorque);
}

void AWheelRig::StepWheels(double Dt)
{
	const FTransform Frame = Body->GetComponentTransform();
	const FVector Up = Frame.GetUnitAxis(EAxis::Z);
	const FVector BodyForward = Frame.GetUnitAxis(EAxis::X);
	const FVector BodyRight = Frame.GetUnitAxis(EAxis::Y);
	const double Reach = Params.RestLengthCm + Params.RadiusCm;

	FCollisionQueryParams Query(TEXT("WheelRig"), false, this);
	TArray<FHitResult> Hits;
	Hits.SetNum(Wheels.Num());
	int32 InContact = 0;
	for (int32 Index = 0; Index < Wheels.Num(); ++Index)
	{
		const FVector Mount = Frame.GetLocation() + Frame.GetRotation().RotateVector(Wheels[Index].MountLocal);
		bool bHit = false;
		if (bUseSweep)
		{
			// Sweep the wheel's sphere from the mount over the suspension travel.
			bHit = GetWorld()->SweepSingleByChannel(Hits[Index], Mount, Mount - Up * Params.RestLengthCm, FQuat::Identity,
				ECC_WorldStatic, FCollisionShape::MakeSphere(Params.RadiusCm), Query);
		}
		else
		{
			bHit = GetWorld()->LineTraceSingleByChannel(Hits[Index], Mount, Mount - Up * Reach, ECC_WorldStatic, Query);
		}
		Hits[Index].bBlockingHit = bHit;
		InContact += bHit ? 1 : 0;
	}

	for (int32 Index = 0; Index < Wheels.Num(); ++Index)
	{
		const FHitResult& Hit = Hits[Index];
		FWheelContact Contact;
		Contact.bHit = Hit.bBlockingHit;
		if (Contact.bHit)
		{
			const FVector Mount = Frame.GetLocation() + Frame.GetRotation().RotateVector(Wheels[Index].MountLocal);
			const FVector Normal = Hit.ImpactNormal.GetSafeNormal();
			Contact.CompressionCm = bUseSweep ? Params.RestLengthCm - Hit.Distance : Reach - Hit.Distance;
			Contact.CompressionRateCmps = -FVector::DotProduct(Body->GetPhysicsLinearVelocityAtPoint(Mount), Up);
			Contact.Forward = (BodyForward - FVector::DotProduct(BodyForward, Normal) * Normal).GetSafeNormal();
			FVector Lateral = BodyRight - FVector::DotProduct(BodyRight, Normal) * Normal;
			Contact.Lateral = (Lateral - FVector::DotProduct(Lateral, Contact.Forward) * Contact.Forward).GetSafeNormal();
			Contact.ContactVelocity = Body->GetPhysicsLinearVelocityAtPoint(Hit.ImpactPoint);
			Contact.MassLongKg = 1.0 / (InverseMassAlong(Hit.ImpactPoint, Contact.Forward) * InContact);
			Contact.MassLatKg = 1.0 / (InverseMassAlong(Hit.ImpactPoint, Contact.Lateral) * InContact);

			FWheelRecord& Record = Records[Index];
			Record.Contact = Contact;
			Record.TargetSpinRadps = Targets.IsValidIndex(Index) ? Targets[Index] : 0.0;
			Record.Result = StepWheel(Params, Contact, Mode, Record.TargetSpinRadps, Dt, Spins[Index]);
			Record.SpinRadps = Spins[Index];
			const FVector Force = Record.Result.NormalForce * Normal + Record.Result.LongForce * Contact.Forward
				+ Record.Result.LatForce * Contact.Lateral;
			Body->AddForceAtLocation(Force, Hit.ImpactPoint);
		}
		else
		{
			FWheelRecord& Record = Records[Index];
			Record.Contact = Contact;
			Record.TargetSpinRadps = Targets.IsValidIndex(Index) ? Targets[Index] : 0.0;
			Record.Result = StepWheel(Params, Contact, Mode, Record.TargetSpinRadps, Dt, Spins[Index]);
			Record.SpinRadps = Spins[Index];
		}
	}
}
