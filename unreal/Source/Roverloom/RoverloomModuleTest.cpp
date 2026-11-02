#include "Misc/AutomationTest.h"
#include "Modules/ModuleManager.h"

#if WITH_DEV_AUTOMATION_TESTS

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FRoverloomModuleLoadedTest,
	"Roverloom.Module.Loaded",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRoverloomModuleLoadedTest::RunTest(const FString& Parameters)
{
	return TestTrue(TEXT("Roverloom module is loaded"), FModuleManager::Get().IsModuleLoaded(TEXT("Roverloom")));
}

#endif
