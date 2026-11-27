#include "RaceOpponent.h"

#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "UObject/ConstructorHelpers.h"

#include "../Bridge/Frames.h"
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

void ARaceOpponent::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
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
