#pragma once

#include "CoreMinimal.h"

namespace Phase7SurfaceUV
{
    // Authored circumference coordinates are periodic. Each render patch has
    // its own vertices, so choose one continuous chart before interpolation.
    // This changes texture coordinates only; native and display positions stay exact.
    inline void UnwrapTriangle(FVector2D& A,FVector2D& B,FVector2D& C)
    {
        FVector2D* Corners[]={&A,&B,&C};
        const double Minimum=FMath::Min3(A.X,B.X,C.X);
        const double Maximum=FMath::Max3(A.X,B.X,C.X);
        if(Maximum-Minimum>.5)
            for(auto* UV:Corners)if(UV->X<.5)UV->X+=1;
        // A single spherical pole has no unique longitude. Give each incident
        // patch its own mean longitude, instead of stretching to authored U=.5.
        for(int I=0;I<3;++I)
            if(FMath::IsNearlyZero(Corners[I]->Y,1e-8)||FMath::IsNearlyEqual(Corners[I]->Y,1.0,1e-8))
                Corners[I]->X=(Corners[(I+1)%3]->X+Corners[(I+2)%3]->X)*.5;
    }

    inline FVector2D Interpolate(FVector2D A,FVector2D B,FVector2D C,const FVector& Weights)
    {
        UnwrapTriangle(A,B,C);
        return A*Weights.X+B*Weights.Y+C*Weights.Z;
    }
}
