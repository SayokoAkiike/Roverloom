#pragma once

#include "CoreMinimal.h"

// The race course, as Python's race.Course.document() writes it to course.json (docs/race.md). Site frame, metres.
// Unreal only draws it: Python alone judges checkpoints, laps and positions.
struct FRaceCourse
{
	FString Name;
	TArray<FVector2D> Checkpoints; // The last one is the start and finish line
	TArray<FBox2D> Sand;
	TArray<FVector2D> Pads;
	bool bHasSupply = false;
	FVector2D Supply = FVector2D::ZeroVector;
	double GateRadiusM = 2.5;
	int32 Laps = 1;
	TArray<FVector2D> Line; // A drivable path through every gate: markers, the minimap and the rock-free corridor
	FVector2D Start = FVector2D::ZeroVector;
	bool bLoop = true; // The start is the last gate
	FString Ground = TEXT("generated");
	FString Style = TEXT("gates"); // "flags": golf-style pin flags at each gate

	bool IsValid() const { return Checkpoints.Num() >= 2; }
};

namespace RoverloomRace
{
	// Reads -RoverCourseFile=<path>. Returns false, and logs why, when it is absent or malformed.
	bool LoadCourse(FRaceCourse& Out);
	// Shortest distance from a site point to the course path, in metres.
	double DistanceToLineM(const FRaceCourse& Course, const FVector2D& P);
	// Loaded once per process and shared by the game mode and the HUD.
	const FRaceCourse& Course();
}
