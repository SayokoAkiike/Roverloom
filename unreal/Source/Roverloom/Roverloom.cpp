#include "Roverloom.h"

#include "Modules/ModuleManager.h"

DEFINE_LOG_CATEGORY(LogRoverloom);

class FRoverloomModule : public FDefaultGameModuleImpl
{
	virtual void StartupModule() override
	{
		UE_LOG(LogRoverloom, Display, TEXT("Roverloom module started"));
	}
};

IMPLEMENT_PRIMARY_GAME_MODULE(FRoverloomModule, Roverloom, "Roverloom");
