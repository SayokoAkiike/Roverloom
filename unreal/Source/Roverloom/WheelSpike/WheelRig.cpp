#include "WheelRig.h"

#include "CollisionQueryParams.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/CollisionProfile.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "HAL/PlatformTime.h"
#include "Misc/FileHelper.h"
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
	Body->SetNotifyRigidBodyCollision(true);
	Body->OnComponentHit.AddDynamic(this, &AWheelRig::OnBodyHit);
}

void AWheelRig::OnBodyHit(UPrimitiveComponent* HitComponent, AActor* OtherActor, UPrimitiveComponent* OtherComp, FVector NormalImpulse,
	const FHitResult& Hit)
{
	++BodyHits;
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
		Records[Index].bStartPenetrating = bHit && Hit.bStartPenetrating;
		if (bHit)
		{
			const FVector Normal = Hit.ImpactNormal.GetSafeNormal();
			// A trace that starts inside geometry reports distance 0, which is full compression: a bump stop.
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
	LastBodyState = BodyState();
	LastTraction.SetNumZeroed(Wheels.Num());
	TArray<FVector2D> Start;
	if (Diagnostics.bWarmStart)
	{
		// Last step's force, onto this step's contact plane. A wheel without contact on either step starts from zero.
		Start.SetNumZeroed(Wheels.Num());
		for (int32 Index = 0; Index < Wheels.Num(); ++Index)
		{
			if (Contacts[Index].bHit)
			{
				Start[Index] = FVector2D(FVector::DotProduct(LastTraction[Index], Contacts[Index].Forward),
					FVector::DotProduct(LastTraction[Index], Contacts[Index].Lateral));
			}
		}
	}
	const TArray<double> SpinsBefore = Spins;
	const double Begin = FPlatformTime::Seconds();
	SolveWheels(Params, LastBodyState, Contacts, Commands, Dt, Spins, Results, Stats, Diagnostics.Options, Start);
	SolveMicros = 1.0e6 * (FPlatformTime::Seconds() - Begin);
	if (!Diagnostics.DumpPath.IsEmpty())
	{
		DumpSolverStep(Diagnostics.DumpPath, Diagnostics.bDumpAppend, Contacts, Commands, Dt, SpinsBefore, Results);
		Diagnostics.DumpPath.Empty();
	}
	if (Diagnostics.bShadow)
	{
		FSolverOptions Strong;
		Strong.MaxPasses = 20000;
		Strong.ToleranceCmps = 1e-10;
		Strong.Order = ESolveOrder::Reverse;
		TArray<double> ShadowSpins = SpinsBefore;
		TArray<FWheelResult> ShadowResults;
		FSolveStats ShadowStats;
		SolveWheels(Params, LastBodyState, Contacts, Commands, Dt, ShadowSpins, ShadowResults, ShadowStats, Strong);
		Shadow = FShadowRecord();
		for (int32 Index = 0; Index < Wheels.Num(); ++Index)
		{
			const double Difference = FVector2D(Results[Index].LongForce - ShadowResults[Index].LongForce,
				Results[Index].LatForce - ShadowResults[Index].LatForce).Size();
			Shadow.ForceDifference = FMath::Max(Shadow.ForceDifference,
				Difference / FMath::Max(Results[Index].FrictionLimit, UE_DOUBLE_SMALL_NUMBER));
		}
		Shadow.NetForceDifference = (Stats.NetForce - ShadowStats.NetForce).Size();
		Shadow.NetTorqueDifference = (Stats.NetTorque - ShadowStats.NetTorque).Size();
		Shadow.NaturalResidual = ShadowStats.NaturalResidual;
		Shadow.Passes = ShadowStats.Iterations;
	}
	for (FVector& Traction : LastTraction)
	{
		Traction = FVector::ZeroVector;
	}
	WheelForce = FVector::ZeroVector;
	WheelTorque = FVector::ZeroVector;

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
			LastTraction[Index] = Results[Index].LongForce * Contact.Forward + Results[Index].LatForce * Contact.Lateral;
			WheelForce += Force;
			WheelTorque += FVector::CrossProduct(Contact.Point - LastBodyState.CenterOfMass, Force);
		}
	}
	if (!ExternalForce.IsZero())
	{
		Body->AddForce(ExternalForce);
	}
}

void AWheelRig::DumpSolverStep(const FString& Path, bool bAppend, TConstArrayView<FWheelContact> Contacts,
	TConstArrayView<FWheelCommand> Commands, double Dt, TConstArrayView<double> SpinsBefore, TConstArrayView<FWheelResult> Results) const
{
	// One line of JSON: the solver's input before the step, and what the engine's solve gave.
	auto Vec = [](const FVector& V) { return FString::Printf(TEXT("[%.17g, %.17g, %.17g]"), V.X, V.Y, V.Z); };
	FString Json = FString::Printf(TEXT("{\"time\": %.17g, \"frame\": %lld, \"dt\": %.17g, \"params\": {\"radius\": %.17g, \"inertia\": %.17g, "
		"\"spring\": %.17g, \"damper\": %.17g, \"friction\": %.17g, \"motor\": %.17g, \"brake\": %.17g}, "), GetWorld()->GetTimeSeconds(),
		static_cast<long long>(GFrameCounter), Dt, Params.RadiusCm, Params.InertiaKgCm2, Params.SpringRate, Params.DamperRate, Params.Friction,
		Params.MotorMaxTorque, Params.BrakeMaxTorque);
	const FBodyState& B = LastBodyState;
	Json += FString::Printf(TEXT("\"body\": {\"inv_mass\": %.17g, \"inv_inertia\": [%s, %s, %s], \"com\": %s, \"v\": %s, \"w\": %s, "
		"\"acc\": %s, \"ext\": %s}, \"wheels\": ["), B.InvMass, *Vec(B.InvInertia[0]), *Vec(B.InvInertia[1]), *Vec(B.InvInertia[2]),
		*Vec(B.CenterOfMass), *Vec(B.LinearVelocity), *Vec(B.AngularVelocity), *Vec(B.Acceleration), *Vec(B.ExternalForce));
	for (int32 Index = 0; Index < Contacts.Num(); ++Index)
	{
		const FWheelContact& C = Contacts[Index];
		const FWheelResult& R = Results[Index];
		Json += FString::Printf(TEXT("%s{\"hit\": %s, \"comp\": %.17g, \"comp_rate\": %.17g, \"point\": %s, \"normal\": %s, \"forward\": %s, "
			"\"lateral\": %s, \"mode\": %d, \"target\": %.17g, \"spin\": %.17g, \"result\": {\"f_long\": %.17g, \"f_lat\": %.17g, "
			"\"motor\": %.17g, \"brake\": %.17g, \"spin\": %.17g}}"), Index ? TEXT(", ") : TEXT(""), C.bHit ? TEXT("true") : TEXT("false"),
			C.CompressionCm, C.CompressionRateCmps, *Vec(C.Point), *Vec(C.Normal), *Vec(C.Forward), *Vec(C.Lateral),
			static_cast<int32>(Commands[Index].Mode), Commands[Index].TargetSpinRadps, SpinsBefore[Index], R.LongForce, R.LatForce,
			R.MotorTorque, R.BrakeTorque, Spins[Index]);
	}
	Json += FString::Printf(TEXT("], \"stats\": {\"passes\": %d, \"converged\": %s, \"last_change\": %.17g, \"natural\": %.17g}}\n"),
		Stats.Iterations, Stats.bConverged ? TEXT("true") : TEXT("false"), Stats.LastChangeCmps, Stats.NaturalResidual);
	FFileHelper::SaveStringToFile(Json, *Path, FFileHelper::EEncodingOptions::AutoDetect, &IFileManager::Get(),
		bAppend ? FILEWRITE_Append : FILEWRITE_None);
}
