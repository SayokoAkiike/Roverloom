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

FBodyState AWheelRig::BodyState() const
{
	const FBodyInstance* Instance = Body->GetBodyInstance();
	const FTransform MassFrame = Instance->GetMassSpaceToWorldSpace();
	const FVector Principal = Instance->GetBodyInertiaTensor();
	const FMatrix Rotation = FRotationMatrix::Make(MassFrame.GetRotation());

	// World inertia, I_w = R diag(I) R^T.
	double World[3][3];
	for (int32 Row = 0; Row < 3; ++Row)
	{
		for (int32 Col = 0; Col < 3; ++Col)
		{
			World[Row][Col] = 0.0;
			for (int32 Axis = 0; Axis < 3; ++Axis)
			{
				World[Row][Col] += Rotation.M[Axis][Row] * Principal[Axis] * Rotation.M[Axis][Col];
			}
		}
	}

	// Locks are on world axes (FBodyInstance::CreateDOFLock with SixDOF). The rotation stays in the free axes' span,
	// so the inverse inertia is that of the free block: P (P^T I_w P)^-1 P^T.
	TArray<int32, TInlineAllocator<3>> Free;
	for (int32 Axis = 0; Axis < 3; ++Axis)
	{
		const bool bLocked = Axis < 2 ? bLockRollPitchAxes : bLockYawAxis;
		if (!bLocked)
		{
			Free.Add(Axis);
		}
	}
	double Inverse[3][3] = {};
	if (Free.Num() == 1)
	{
		Inverse[Free[0]][Free[0]] = 1.0 / World[Free[0]][Free[0]];
	}
	else if (Free.Num() == 2)
	{
		const int32 A = Free[0];
		const int32 B = Free[1];
		const double Det = World[A][A] * World[B][B] - World[A][B] * World[B][A];
		Inverse[A][A] = World[B][B] / Det;
		Inverse[B][B] = World[A][A] / Det;
		Inverse[A][B] = -World[A][B] / Det;
		Inverse[B][A] = -World[B][A] / Det;
	}
	else if (Free.Num() == 3)
	{
		for (int32 Row = 0; Row < 3; ++Row)
		{
			for (int32 Col = 0; Col < 3; ++Col)
			{
				for (int32 Axis = 0; Axis < 3; ++Axis)
				{
					Inverse[Row][Col] += Rotation.M[Axis][Row] * Rotation.M[Axis][Col] / Principal[Axis];
				}
			}
		}
	}

	FBodyState State;
	State.InvMass = 1.0 / Instance->GetBodyMass();
	for (int32 Row = 0; Row < 3; ++Row)
	{
		State.InvInertia[Row] = FVector(Inverse[Row][0], Inverse[Row][1], Inverse[Row][2]);
	}
	State.CenterOfMass = MassFrame.GetLocation();
	State.LinearVelocity = Body->GetPhysicsLinearVelocity();
	State.AngularVelocity = Body->GetPhysicsAngularVelocityInRadians();
	State.Acceleration = FVector(0.0, 0.0, GetWorld()->GetGravityZ());
	State.ExternalForce = ExternalForce;
	return State;
}

void AWheelRig::StepWheels(double Dt)
{
	const FTransform Frame = Body->GetComponentTransform();
	const FVector Up = Frame.GetUnitAxis(EAxis::Z);
	const FVector BodyForward = Frame.GetUnitAxis(EAxis::X);
	const FVector BodyRight = Frame.GetUnitAxis(EAxis::Y);
	const double Reach = Params.RestLengthCm + Params.RadiusCm;

	FCollisionQueryParams Query(TEXT("WheelRig"), false, this);
	TArray<RoverloomWheel::FWheelContact> Contacts;
	TArray<FWheelCommand> Commands;
	Contacts.SetNum(Wheels.Num());
	Commands.SetNum(Wheels.Num());
	for (int32 Index = 0; Index < Wheels.Num(); ++Index)
	{
		const FVector Mount = Frame.GetLocation() + Frame.GetRotation().RotateVector(Wheels[Index].MountLocal);
		FHitResult Hit;
		bool bHit = false;
		if (bUseSweep)
		{
			// Sweep the wheel's sphere from the mount over the suspension travel.
			bHit = GetWorld()->SweepSingleByChannel(Hit, Mount, Mount - Up * Params.RestLengthCm, FQuat::Identity,
				ECC_WorldStatic, FCollisionShape::MakeSphere(Params.RadiusCm), Query);
		}
		else
		{
			bHit = GetWorld()->LineTraceSingleByChannel(Hit, Mount, Mount - Up * Reach, ECC_WorldStatic, Query);
		}
		Commands[Index].Mode = Mode;
		Commands[Index].TargetSpinRadps = Targets.IsValidIndex(Index) ? Targets[Index] : 0.0;

		FWheelContact& Contact = Contacts[Index];
		Contact.bHit = bHit;
		if (bHit)
		{
			const FVector Normal = Hit.ImpactNormal.GetSafeNormal();
			Contact.CompressionCm = bUseSweep ? Params.RestLengthCm - Hit.Distance : Reach - Hit.Distance;
			Contact.CompressionRateCmps = -FVector::DotProduct(Body->GetPhysicsLinearVelocityAtPoint(Mount), Up);
			Contact.Point = Hit.ImpactPoint;
			Contact.Normal = Normal;
			Contact.Forward = (BodyForward - FVector::DotProduct(BodyForward, Normal) * Normal).GetSafeNormal();
			FVector Lateral = BodyRight - FVector::DotProduct(BodyRight, Normal) * Normal;
			Contact.Lateral = (Lateral - FVector::DotProduct(Lateral, Contact.Forward) * Contact.Forward).GetSafeNormal();
		}
	}

	TArray<FWheelResult> Results;
	SolveWheels(Params, BodyState(), Contacts, Commands, Dt, Spins, Results, Stats);

	for (int32 Index = 0; Index < Wheels.Num(); ++Index)
	{
		const FWheelContact& Contact = Contacts[Index];
		FWheelRecord& Record = Records[Index];
		Record.Contact = Contact;
		Record.TargetSpinRadps = Commands[Index].TargetSpinRadps;
		Record.Result = Results[Index];
		Record.SpinRadps = Spins[Index];
		if (Contact.bHit)
		{
			const FVector Force = Results[Index].NormalForce * Contact.Normal + Results[Index].LongForce * Contact.Forward
				+ Results[Index].LatForce * Contact.Lateral;
			Body->AddForceAtLocation(Force, Contact.Point);
		}
	}
	if (!ExternalForce.IsZero())
	{
		Body->AddForce(ExternalForce);
	}
}
