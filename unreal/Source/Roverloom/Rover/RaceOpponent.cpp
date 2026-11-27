#include "RaceOpponent.h"

#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "PhysicalMaterials/PhysicalMaterial.h"
#include "PhysicsEngine/PhysicsSettings.h"
#include "UObject/ConstructorHelpers.h"

#include "../Bridge/Frames.h"
#include "../Roverloom.h"
#include "../WheelSpike/WheelRig.h"
#include "Greybox.h"
#include "RoverDrive.h"

namespace
{
	UStaticMeshComponent* AddPart(AActor* Owner, USceneComponent* Parent, const TCHAR* Name, UStaticMesh* Mesh, const FVector& At,
		const FRotator& Rotation, const FVector& SizeCm)
	{
		UStaticMeshComponent* Part = Owner->CreateDefaultSubobject<UStaticMeshComponent>(Name);
		Part->SetupAttachment(Parent);
		Part->SetStaticMesh(Mesh);
		Part->SetRelativeLocationAndRotation(At, Rotation);
		Part->SetRelativeScale3D(SizeCm / 100.0);
		Part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Part->SetGenerateOverlapEvents(false);
		Part->SetCanEverAffectNavigation(false);
		return Part;
	}
}

ARaceOpponent::ARaceOpponent()
{
	PrimaryActorTick.bCanEverTick = true;
	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(Root);
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeMesh(TEXT("/Engine/BasicShapes/Cube.Cube"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CylinderMesh(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	UStaticMesh* Cube = CubeMesh.Object;
	UStaticMesh* Cylinder = CylinderMesh.Object;
	const FVector Body = RoverloomRover::BodySizeCm;
	// Body, deck panel and mast in the rover's proportions; index 0 takes the paint.
	Meshes.Add(AddPart(this, Root, TEXT("Body"), Cube, FVector(0, 0, 0), FRotator::ZeroRotator, Body));
	Meshes.Add(AddPart(this, Root, TEXT("Deck"), Cube, FVector(-20, 0, Body.Z / 2 + 4), FRotator::ZeroRotator, FVector(150, 130, 6)));
	Meshes.Add(AddPart(this, Root, TEXT("Mast"), Cylinder, FVector(70, 0, 80), FRotator::ZeroRotator, FVector(8, 8, 120)));
	Meshes.Add(AddPart(this, Root, TEXT("MastHead"), Cube, FVector(75, 0, 145), FRotator::ZeroRotator, FVector(22, 36, 16)));
	for (int32 I = 0; I < RoverloomRover::NumWheels; ++I)
	{
		const FVector Mount = RoverloomRover::WheelMountCm(I);
		const double R = RoverloomRover::WheelRadiusCm;
		Meshes.Add(AddPart(this, Root, *FString::Printf(TEXT("Wheel%d"), I), Cylinder, FVector(Mount.X, Mount.Y, -RoverloomRover::RideHeightCm + R),
			FRotator(0, 0, 90), FVector(2 * R, 2 * R, 25)));
		WheelSpin.Add(0.0);
	}
}

void ARaceOpponent::SetTarget(const FVector2D& SiteM, double SiteYawRad, const FLinearColor& Paint, bool bGhost)
{
	TargetCm = RoverloomFrames::SiteToUnrealPosition(FVector(SiteM.X, SiteM.Y, 0.0));
	TargetYawDeg = -FMath::RadiansToDegrees(SiteYawRad); // Unreal's Y is the site's -Y, so yaw changes sign
	if (!bHasTarget)
	{
		bHasTarget = true;
		SetActorLocationAndRotation(FVector(TargetCm.X, TargetCm.Y, GroundCm + RoverloomRover::RideHeightCm), FRotator(0, TargetYawDeg, 0));
	}
	bIsGhost = bGhost;
	if (!bPainted || !Paint.Equals(LastPaint))
	{
		bPainted = true;
		LastPaint = Paint;
		const FLinearColor Body = bGhost ? FMath::Lerp(Paint, FLinearColor(0.85f, 0.9f, 0.95f), 0.55f) : Paint;
		const FLinearColor Dark(0.06f, 0.06f, 0.07f);
		const FLinearColor Light(0.72f, 0.7f, 0.66f);
		for (int32 I = 0; I < Meshes.Num(); ++I)
		{
			RoverloomGreybox::Paint(Meshes[I], I == 0 ? Body : I == 1 ? Dark : I < 4 ? Light : Dark, I == 0 ? 0.55f : 0.85f);
		}
	}
}

double ARaceOpponent::GroundBelowCm(const FVector& AtCm) const
{
	FHitResult Hit;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(RaceOpponentGround), false, this);
	if (Rig) Params.AddIgnoredActor(Rig);
	if (GetWorld()->LineTraceSingleByObjectType(Hit, FVector(AtCm.X, AtCm.Y, AtCm.Z + 3000.0), FVector(AtCm.X, AtCm.Y, AtCm.Z - 10000.0),
			FCollisionObjectQueryParams(ECC_WorldStatic), Params))
	{
		return Hit.ImpactPoint.Z;
	}
	return GroundCm;
}

void ARaceOpponent::EnablePhysics()
{
	if (Rig || bIsGhost)
	{
		return;
	}
	const FVector At(TargetCm.X, TargetCm.Y, GetActorLocation().Z);
	GroundCm = GroundBelowCm(At);
	const FVector Spawn(TargetCm.X, TargetCm.Y, GroundCm + RoverloomRover::RideHeightCm);
	ResetPose = FTransform(FRotator(0.0, TargetYawDeg, 0.0), Spawn);
	RigMaterial = NewObject<UPhysicalMaterial>(this);
	RigMaterial->Friction = RoverloomRover::Friction;
	RigMaterial->StaticFriction = RoverloomRover::Friction;
	RigMaterial->Restitution = RoverloomRover::RaceRestitution;
	FActorSpawnParameters SpawnParams;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	Rig = GetWorld()->SpawnActor<AWheelRig>(AWheelRig::StaticClass(), Spawn, ResetPose.Rotator(), SpawnParams);
	if (!Rig)
	{
		return;
	}
	TArray<AWheelRig::FWheelSetup> Setups;
	for (int32 Index = 0; Index < RoverloomRover::NumWheels; ++Index)
	{
		Setups.Add({RoverloomRover::WheelMountCm(Index), Index < 3});
	}
	// The player's rig: free rotation, sphere sweeps, 853.5 kg, friction 0.6.
	Rig->Build(RoverloomRover::BodySizeCm, RoverloomRover::MassKg, Setups, false, false, true, RoverloomRover::Friction, RigMaterial);
	Rig->SetWheelsHitOnlyStatic(true);
	Rig->GetBody()->SetVisibility(false); // the look-alike meshes are drawn instead; collision is the rig's box
	SetActorLocationAndRotation(Spawn, ResetPose.Rotator());
}

void ARaceOpponent::SetCommand(double LinearMps, double YawRateRadps)
{
	// The rover's limits, with room for a boost (1.5 times); Python already keeps within them.
	const double MaxMps = RoverloomRover::MaxSpeedMps * 1.5;
	CommandMps = FMath::IsFinite(LinearMps) ? FMath::Clamp(LinearMps, -MaxMps, MaxMps) : 0.0;
	CommandRadps = FMath::IsFinite(YawRateRadps)
		? FMath::Clamp(YawRateRadps, -RoverloomRover::MaxYawRateRadps, RoverloomRover::MaxYawRateRadps)
		: 0.0;
}

bool ARaceOpponent::IsFree(const FVector& AtCm, const FQuat& Rotation) const
{
	// The rig's box with a margin, raised clear of the ground: free if no solid object or rover is inside it
	FCollisionQueryParams Params(SCENE_QUERY_STAT(RaceOpponentFree), false, this);
	if (Rig) Params.AddIgnoredActor(Rig);
	FCollisionObjectQueryParams Objects;
	Objects.AddObjectTypesToQuery(ECC_WorldStatic);
	Objects.AddObjectTypesToQuery(ECC_WorldDynamic);
	Objects.AddObjectTypesToQuery(ECC_PhysicsBody);
	const FVector Half = RoverloomRover::BodySizeCm * 0.5 + FVector(30.0, 30.0, 0.0);
	return !GetWorld()->OverlapAnyTestByObjectType(AtCm + FVector(0.0, 0.0, 20.0), Rotation, Objects, FCollisionShape::MakeBox(Half), Params);
}

void ARaceOpponent::ResetTo(const FVector2D& SiteM, double SiteYawRad)
{
	// The asked pose, or the first free place beside it: rocks, props and rovers are found by the overlap test, so no
	// list of their positions is needed.
	const FRotator Facing(0.0, -FMath::RadiansToDegrees(SiteYawRad), 0.0);
	const FVector Base = RoverloomFrames::SiteToUnrealPosition(FVector(SiteM.X, SiteM.Y, 0.0));
	const FVector Right = FRotationMatrix(Facing).GetUnitAxis(EAxis::Y);
	FVector Chosen = FVector::ZeroVector;
	bool bFound = false;
	for (const double OffsetCm : {0.0, 250.0, -250.0, 500.0, -500.0, 750.0, -750.0})
	{
		const FVector At = Base + Right * OffsetCm;
		const FVector Pose(At.X, At.Y, GroundBelowCm(FVector(At.X, At.Y, GetActorLocation().Z)) + RoverloomRover::RideHeightCm);
		if (OffsetCm == 0.0) Chosen = Pose;
		if (IsFree(Pose, Facing.Quaternion()))
		{
			Chosen = Pose;
			bFound = true;
			break;
		}
	}
	if (!bFound)
	{
		UE_LOG(LogRoverloom, Warning, TEXT("Race: no free place beside the reset point for %s; reset there anyway"), *DisplayName);
	}
	ResetPose = FTransform(Facing, Chosen);
	if (!Rig)
	{
		return;
	}
	UStaticMeshComponent* Body = Rig->GetBody();
	Body->SetWorldLocationAndRotation(ResetPose.GetLocation(), ResetPose.GetRotation(), false, nullptr, ETeleportType::ResetPhysics);
	Body->SetPhysicsLinearVelocity(FVector::ZeroVector);
	Body->SetPhysicsAngularVelocityInDegrees(FVector::ZeroVector);
	CommandMps = CommandRadps = 0.0;
}

bool ARaceOpponent::GetSitePose(FVector2D& OutM, double& OutYawRad, double& OutForwardMps) const
{
	if (!Rig || !bRigReady)
	{
		return false;
	}
	const UStaticMeshComponent* Body = Rig->GetBody();
	const FVector P = RoverloomFrames::UnrealToSitePosition(Body->GetComponentLocation());
	OutM = FVector2D(P.X, P.Y);
	OutYawRad = -FMath::DegreesToRadians(Body->GetComponentRotation().Yaw); // Unreal's Y is the site's -Y
	OutForwardMps = FVector::DotProduct(Body->GetPhysicsLinearVelocity(), Body->GetForwardVector()) / RoverloomFrames::UnrealCmPerM;
	return FMath::IsFinite(OutM.X) && FMath::IsFinite(OutM.Y) && FMath::IsFinite(OutYawRad);
}

void ARaceOpponent::SenseAhead()
{
	const UStaticMeshComponent* Body = Rig->GetBody();
	const FVector Center = Body->GetComponentLocation();
	const double YawDeg = Body->GetComponentRotation().Yaw;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(RaceOpponentSense), false, this);
	Params.AddIgnoredActor(Rig);
	FCollisionObjectQueryParams Objects;
	Objects.AddObjectTypesToQuery(ECC_WorldStatic);
	Objects.AddObjectTypesToQuery(ECC_WorldDynamic);
	Objects.AddObjectTypesToQuery(ECC_PhysicsBody);
	// Ahead: a box as wide as the body (anything it would hit); the sides: a 30 cm sphere 30 degrees out
	const FCollisionShape SideProbe = FCollisionShape::MakeSphere(30.0f);
	const FCollisionShape AheadProbe = FCollisionShape::MakeBox(FVector(10.0, RoverloomRover::BodySizeCm.Y * 0.5, 25.0));
	const double RangeCm = SenseRangeM * 100.0;
	// Site left is Unreal's negative yaw (Unreal's Y is the site's -Y)
	const double OffsetsDeg[3] = {-30.0, 0.0, 30.0};
	for (int32 I = 0; I < 3; ++I)
	{
		const FVector Dir = FRotator(0.0, YawDeg + OffsetsDeg[I], 0.0).Vector();
		// From the front of the body, 45 cm above the ground: low enough for cairns and rocks, below the deck
		const FVector From = Center + Dir * (RoverloomRover::BodySizeCm.X * 0.5) - FVector(0.0, 0.0, RoverloomRover::RideHeightCm - 45.0);
		TArray<FHitResult> Hits;
		const bool bAhead = I == 1;
		GetWorld()->SweepMultiByObjectType(Hits, From, From + Dir * RangeCm, bAhead ? FRotator(0.0, YawDeg, 0.0).Quaternion() : FQuat::Identity,
			Objects, bAhead ? AheadProbe : SideProbe, Params);
		double Free = SenseRangeM;
		for (const FHitResult& Hit : Hits)
		{
			// Ground the rover can drive up faces upward; an obstacle has a steep face
			if (Hit.ImpactNormal.Z > 0.7 || Hit.bStartPenetrating) continue;
			Free = FMath::Min(Free, Hit.Distance / 100.0);
			break;
		}
		Clearance[I] = Free;
	}
}

void ARaceOpponent::TickPhysical(double DeltaSeconds)
{
	UStaticMeshComponent* Body = Rig->GetBody();
	if (!bRigReady)
	{
		// The body simulates from the frame IsReady first returns true, as the player's rig.
		bRigReady = Rig->IsReady();
		if (bRigReady)
		{
			Rig->AddWheelContactShapes();
		}
		SetActorLocationAndRotation(Body->GetComponentLocation(), Body->GetComponentQuat());
		return;
	}
	const FVector Location = Body->GetComponentLocation();
	if (Location.ContainsNaN() || Location.Z < ResetPose.GetLocation().Z - 2000.0)
	{
		// Fallen through the ground or diverged: back to the last reset pose
		const FVector Site = RoverloomFrames::UnrealToSitePosition(ResetPose.GetLocation());
		ResetTo(FVector2D(Site.X, Site.Y), -FMath::DegreesToRadians(ResetPose.Rotator().Yaw));
		return;
	}
	RoverloomCommand::FAction Action;
	Action.LinearVelocityMps = CommandMps;
	Action.YawRateRadps = CommandRadps;
	TArray<double> Targets;
	RoverloomRover::SkidSteerTargets(Action, Targets, RoverloomRover::DriveTrackScale);
	Rig->SetTargets(Targets, Action.IsStop() ? RoverloomWheel::EWheelMode::Brake : RoverloomWheel::EWheelMode::Drive);
	// As the player's rover: the wheel solve uses Chaos's clamped step
	const double StepDt = FMath::Min(DeltaSeconds, static_cast<double>(UPhysicsSettings::Get()->MaxPhysicsDeltaTime));
	Rig->StepWheels(StepDt);
	SetActorLocationAndRotation(Body->GetComponentLocation(), Body->GetComponentQuat());
	SenseAhead();
	// Wheels where the suspension holds them, spinning at the rig's wheel speed
	const TArray<AWheelRig::FWheelRecord>& Records = Rig->GetRecords();
	const double RestCm = Rig->GetParams().RestLengthCm;
	for (int32 I = 0; I < WheelSpin.Num() && I < Records.Num(); ++I)
	{
		const AWheelRig::FWheelRecord& Record = Records[I];
		const double Compression = Record.Contact.bHit ? FMath::Clamp(Record.Contact.CompressionCm, 0.0, RestCm) : 0.0;
		const FVector Mount = RoverloomRover::WheelMountCm(I);
		WheelSpin[I] = FMath::Fmod(WheelSpin[I] + FMath::RadiansToDegrees(Record.SpinRadps * DeltaSeconds), 360.0);
		Meshes[4 + I]->SetRelativeLocationAndRotation(FVector(Mount.X, Mount.Y, Mount.Z - (RestCm - Compression)),
			FQuat(FRotator(-WheelSpin[I], 0.0, 0.0)) * FQuat(FRotator(0.0, 0.0, 90.0)));
	}
}

void ARaceOpponent::Destroyed()
{
	if (Rig)
	{
		Rig->Destroy();
		Rig = nullptr;
	}
	Super::Destroyed();
}

void ARaceOpponent::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (Rig)
	{
		TickPhysical(DeltaSeconds);
		return;
	}
	if (!bHasTarget)
	{
		return;
	}
	// The ground below, every few frames: Landscape or greybox blocks, never another rover (they have no collision).
	if ((TraceFrame++ % 4) == 0)
	{
		FHitResult Hit;
		const FVector At = GetActorLocation();
		FCollisionQueryParams Params(SCENE_QUERY_STAT(RaceOpponentGround), false, this);
		if (GetWorld()->LineTraceSingleByObjectType(Hit, FVector(At.X, At.Y, At.Z + 3000.0), FVector(At.X, At.Y, At.Z - 10000.0),
				FCollisionObjectQueryParams(ECC_WorldStatic), Params))
		{
			GroundCm = Hit.ImpactPoint.Z;
		}
	}
	const FVector Now = GetActorLocation();
	const FVector Goal(TargetCm.X, TargetCm.Y, GroundCm + RoverloomRover::RideHeightCm);
	const FVector Next = FMath::VInterpTo(Now, Goal, DeltaSeconds, 6.0f);
	const FRotator Rot = FMath::RInterpTo(GetActorRotation(), FRotator(0, TargetYawDeg, 0), DeltaSeconds, 6.0f);
	SetActorLocationAndRotation(Next, Rot);
	// Spin the wheels with the distance moved, for the look of rolling.
	const double Moved = FVector::Dist2D(Now, Next);
	for (int32 I = 0; I < WheelSpin.Num(); ++I)
	{
		WheelSpin[I] += FMath::RadiansToDegrees(Moved / RoverloomRover::WheelRadiusCm);
		// As ARoverPawn::UpdateWheels: spin about the axle, then lay the cylinder on its side.
		Meshes[4 + I]->SetRelativeRotation(FQuat(FRotator(-WheelSpin[I], 0.0, 0.0)) * FQuat(FRotator(0.0, 0.0, 90.0)));
	}
}
