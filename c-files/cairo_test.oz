functor

import
    Cairo at 'x-oz://boot/cairo.ozf'

define
    Pi = 3.141592653589793

    Xc = 128.0
    Yc = 128.0
    Radius = 100.0
    Angle1 = 45.0 * (Pi / 180.0)
    Angle2 = 45.0 * (Pi / 180.0)

    Surface = {Cairo.imageSurfaceCreate argb32 256 256}
    Cr = {Cairo.create Surface}

    {Cairo.setLineWidth Cr 10.0}
    {Cairo.arc Cr Xc Yc Radius Angle1 Angle2}
    {Cairo.stroke Cr}

    % Draw helping lines
    {Cairo.setSourceRgba Cr 1.0 0.2 0.2 0.6}
    {Cairo.setLineWidth Cr 6.0}

    {Cairo.arc Cr Xc Yc 10.0 0.0 2*Pi}
    {Cairo.fill Cr}

    {Cairo.arc Cr Xc Yc Radius Angle1 Angle1}
    {Cairo.lineTo Cr Xc Yc}
    {Cairo.arc Cr Xc Yc Radius Angle2 Angle2}
    {Cairo.lineTo Cr Xc Yc}
    {Cairo.stroke Cr}

    {Cairo.surfaceWriteToPng Surface "/tmp/result.png"}
    {Cairo.surfaceDestroy Surface}
    {Cairo.destroy Cr}
end

