Activate the **California CDTFA** provider in the US Tax → Providers list (or
*Settings → US Sales Tax Engine*). No API key is required.

With the engine in *Hybrid* mode, California addresses resolve through CDTFA's
rooftop service (priority 20, after the local SST database); other states fall
through to the next provider in the chain. The engine caches each rate result
(per its configured cache TTL), so repeat sales to the same California address
within that window resolve from the cache without another CDTFA call.

CDTFA returns a single combined rate per California Tax Area Code; this provider
books the 7.25% statewide base as the state line and the rooftop remainder as a
named district line. The combined total is exact.
