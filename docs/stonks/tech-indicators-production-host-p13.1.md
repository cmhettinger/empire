# Production Host Sizing And Procurement Review (P13.1)

Date: 2026-09-04. Status: complete; the owner selected and ordered the in-place
`hub-1` upgrade, with delivery expected 2026-09-05. Installation and acceptance
remain P13.2-P13.7 work.

The owner requires **new purchased components**, a compact mini-PC form factor,
and the lowest practical complete purchase price; reusing the already-owned
`hub-1` is now allowed. HPE is optional. The current direction is a **64 GB
Empire production host with at least 2 TB of added local SSD capacity**, then a
separate AI host later. All non-macOS devices must run **Ubuntu Server LTS**.
The earlier complete-host and 128 GB combined-host quotes remain comparison
evidence. The selected production host is `hub-1`; 128 GB is not a universal
Ollama minimum.
These instructions supersede the vendor wording in the historical development
evidence, without changing its gates.

## Selected Direction And Rationale

Production remains separate from inference. The owner selected 64 GB RAM and
2 TB added NVMe capacity. The earlier request prioritized a faster CPU, but the
2026-09-04 cost-containment decision accepts the existing processor
for up to one year only if measured production results pass unchanged gates.
The earlier eight-core Ryzen 7 255 is no longer the preferred new-host CPU tier.
Compare measured single-thread and sustained concurrent performance, with
replaceable storage and preferably at least 2.5 GbE. Use Ubuntu Server LTS with
native Docker Engine and Compose. A dedicated GPU is unnecessary for Empire's
current workload. Select the future AI machine against measured model quality,
latency, GPU-accessible memory, and supported drivers when that work is ready.

This removes inference memory/thermal contention from production and allows
independent AI upgrades/reboots. Future integration should use an explicit
network endpoint and bounded timeouts; AI unavailability must not block the
existing deterministic ingestion/technical pipeline. Routing is not implemented
by P13.1. Two hosts add power use and maintenance, so no lower lifetime cost is
claimed before the second machine is selected.

The 2026-09-04 selected cost-containment option reuses `hub-1` for one year,
subject to confirming its free second M.2 slot and passing the existing
production gates after the ordered 64 GB / 2 TB upgrade. The original
$764.99–$1,159 options remain Empire-only price references, but
their 512 GB/1 TB storage needs a fresh 2 TB complete quote. The HP example
already lists 64 GB/2 TB, subject to its unresolved seller/support terms.
The replacement HP and Framework remain comparison evidence rather than the
selected path. No alternative-host comparison is a claim of M4 Pro CPU parity.
The owner subsequently confirmed 64 GB is sufficient and emphasized avoiding
a CPU responsiveness downgrade from the development Mac. The Ryzen 7 255 is
a budget capacity candidate, not a demonstrated performance match; see the
measured host identity and published benchmark comparison below.
The owner raised support/reliability concerns about BOSGAME; its lower price
alone establishes neither poor reliability nor equivalence to other vendors.
BOSGAME M5 AI and GMKtec M5 Ultra are different machines despite similar names.

The unselected complete-host configurations are comparison candidates, not a
claim that any untested host passes Empire's production performance gates or
is the cheapest offer anywhere.

### Reuse Candidate: Upgrade `hub-1`

The live host inventory confirms an HP Elite Mini 805 G8 Desktop PC (`SBKPF`)
running Ubuntu 26.04 LTS and kernel 7.0.0-27 with a Ryzen 5 PRO 5650G, 16 GB
RAM, and a 512 GB-class SSD. [HP's G8 specifications](https://support.hp.com/gb-en/document/ish_4597643-4597687-16)
list two user-accessible DDR4-3200 SODIMM slots, a supported maximum of 64 GB
as 2 × 32 GB, and M.2 2280 PCIe NVMe storage through 2 TB. The platform has two
M.2 2280 storage sockets. Confirm the second socket is present, empty, and has
its retaining screw before opening the ordered SSD package or beginning the
installation.

The current RAM is one Timetec `TIMETEC-SD4-2666` 16 GB module configured at
2,667 MT/s in channel A; channel B is empty. The proposed matched kit replaces
that module, raises capacity to 64 GB, and enables dual-channel DDR4-3200.
Ubuntu currently exposes 14.43 GiB of the nominal 16 GB, so acceptance must
measure OS-visible memory and reduce the 64 GiB planning allocations if the
same firmware/iGPU reservation remains after the upgrade.

The current `SAMSUNG MZAL8512HFLU-00BL2` boot SSD reports 37 °C, zero critical
warnings, zero media/data-integrity errors, 100% available spare, and 0% used
endurance. It has 433 GiB free. Retaining it as the boot/runtime drive is
reasonable. Only one NVMe namespace is visible to Ubuntu, consistent with an
unused second socket but not proof that its retaining hardware is installed.
BIOS T26 02.17.00 dated 2025-07-08 matches HP's published minimum remediation
version for this model; recheck the current HP catalog during the P13.2 baseline.

The proposed new parts were rechecked on Amazon on 2026-09-04:

| Part | Fit and role | Observed price |
|---|---|---:|
| [Crucial CT2K32G4SFD832A](https://www.amazon.com/dp/B07ZLCVKPV?th=1), 64 GB kit (2 × 32 GB) | DDR4-3200, CL22, 1.2 V, non-ECC, unbuffered, 260-pin SODIMM; replaces the installed RAM | $468.00 |
| [WD_BLACK SN7100 WDS200T4X0E](https://www.amazon.com/dp/B0DN6ZQ3PD?th=1), 2 TB | Bare M.2 2280 PCIe 4.0 NVMe TLC SSD; install in the free storage socket | $309.99 |
| **Parts subtotal before tax** | Existing 512 GB boot SSD retained; about 2.5 TB raw local storage total | **$777.99** |

The RAM specifications match HP's supported 64 GB configuration. Amazon showed
the new kit sold and shipped by Memorybank; at $468 it is compatible but poor
value and should be re-quoted against a reputable matched 2 × 32 GB JEDEC kit.
Do not mix it with the current modules. The SSD offer was shipped by Amazon and
sold by DealX. [Sandisk specifies](https://support-eu.sandisk.com/app/answers/detailweb/a_id/30797/~/wd-internal-ssd-endurance-and-warranty-periods)
1,200 TBW or five years, whichever comes first. The drive will negotiate to the
system's supported speed: [AMD specifies PCIe 3.0 for the 5650G](https://www.amd.com/en/support/downloads/drivers.html/processors/ryzen-pro/ryzen-pro-5000-series/amd-ryzen-5-pro-5650g.html),
so its advertised PCIe 4.0 maximum is unused capacity, not an incompatibility.
Its endurance, TLC flash, and lack of a bulky heatsink suit a database-data
drive; still compare its price with other reputable 2 TB TLC NVMe drives.

Current new-memory vendor comparison, rechecked 2026-09-04:

| Vendor / exact part | Seller and support evidence | Price before tax |
|---|---|---:|
| [Timetec 64 GB dual-rank kit](https://www.amazon.com/dp/B08KRXFM4R), 2 × 32 GB DDR4-3200 CL22 2Rx8 | Amazon offer labeled Timetec International Inc; page advertises lifetime warranty and U.S. technical support | **$400.99** |
| [Crucial CT2K32G4SFD832A at Provantage](https://www.provantage.com/crucial-technology-ct2k32g4sfd832a~7CIAL7WV.htm) | Factory new; Provantage states it is an authorized Crucial dealer and lists a lifetime limited warranty | **$477.63** |
| [OWC 3S2D42R8064P direct](https://eshop.macsales.com/item/OWC/3S2D42R8064P/) | Direct seller; lifetime limited warranty, advanced replacement, and 30-day money-back policy | **$479.50 shown as business price** |
| [Crucial CT2K32G4SFD832A at B&H](https://www.bhphotovideo.com/c/product/1600343-REG/crucial_ct2k32g4sfd832a_2_32gb_ddr4_3200_sodimm_1_2v.html) | Authorized dealer; exact matched kit | **$549.00** |

All four have the required 2 × 32 GB, DDR4-3200, 260-pin, 1.2 V, non-ECC,
unbuffered SODIMM characteristics. The Timetec kit is the recommended current
value option: it is $67.01 below the linked Crucial Amazon offer, uses the same
brand already operating in `hub-1`, and is sold under the brand-named Amazon
seller with an advertised lifetime warranty. It makes the recommended RAM plus
SN7100 subtotal **$710.98** before tax, saving **$1,388.02** versus the $2,099
replacement HP. Confirm seller, new condition, warranty, stock, and checkout
price immediately before purchase. Avoid marketplace offers that do not name
the manufacturer part, module count, voltage, ECC status, and return coverage.

Rush-delivery Amazon comparison, rechecked 2026-09-04 for the page's default
Ashburn 20147 destination (Prime delivery shown for 2026-09-05):

| Exact offer | Compatibility and channel | Price before tax | Decision |
|---|---|---:|---|
| [PNY MN64GK2D43200-TB](https://www.amazon.com/dp/B0CFYT36QM/), 64 GB (2 × 32 GB) DDR4-3200 CL22 | 260-pin, 1.2 V, non-ECC SODIMM; shipped and sold by Amazon.com | **$411.99** | **Preferred rush option** |
| [Gigastone B09478SXD7](https://www.amazon.com/dp/B09478SXD7/), 64 GB (2 × 32 GB) DDR4-3200 CL22 | 260-pin, 1.2 V, non-ECC unbuffered SODIMM; shipped by Amazon and sold by Gigastone America | **$448.99** | Compatible, but costs more than PNY and the listing showed only seven ratings |
| [Timetec B09BH51XX2](https://www.amazon.com/dp/B09BH51XX2/), 64 GB (2 × 32 GB) DDR4-3200 CL22 2Rx8 | Listing explicitly specifies ECC; HP documents non-ECC memory for this system | **$429.99** | Reject for this host |
| [Crucial CP2K32G4DFRA32A](https://www.amazon.com/dp/B0C29W4G29/), 64 GB (2 × 32 GB) DDR4-3200 | 288-pin desktop UDIMM, sold by marketplace seller STOCKYFY | **$554.00** | Physically incompatible; reject |

The PNY kit is the lowest-priced compatible next-day offer in this set and has
the cleanest fulfillment channel. Delivery dates remain address-, account-, and
checkout-dependent; verify the destination-specific promise before submitting
the order.

### Selected And Ordered Upgrade

On 2026-09-04 the owner ordered these new components for `hub-1`, with the
Amazon order showing arrival on 2026-09-05:

| Ordered component | Accepted role and support terms | Planning price before tax |
|---|---|---:|
| [PNY MN64GK2D43200-TB](https://www.amazon.com/dp/B0CFYT36QM), 64 GB (2 × 32 GB) DDR4-3200 CL22 notebook kit | Replace the installed 16 GB module; PNY publishes a limited lifetime original-purchaser memory warranty, subject to its authorized-channel terms | $411.99 |
| [WD_BLACK SN7100 WDS200T4X0E](https://www.amazon.com/dp/B0DN6ZQ3PD), 2 TB M.2 2280 NVMe TLC SSD | Add as the Empire data drive; Sandisk publishes five-year/1,200-TBW coverage, whichever comes first | $309.99 |
| **Planning subtotal** | Actual charged total and tax remain in the private order record | **$721.98** |

The purchase accepts consumer return/mail-in support rather than an onsite
server SLA. Retain the order invoice and serial-number records for warranty
claims. P13.2 must inspect the empty M.2 position and retaining hardware before
opening the SSD packaging, then install and test both parts while the retailer
return window is available. After installation, both SODIMM slots will contain
the matched PNY kit and the platform will be at HP's documented 64 GB maximum.
Both M.2 positions will be occupied by the retained 512 GB boot drive and the
new 2 TB data drive; future local expansion therefore requires drive
replacement or external/NAS storage.

The selected $721.98 planning subtotal saves $1,377.02 before tax versus the
$2,099 assembled HP replacement and
keeps a known Ubuntu host. Six Zen 3 cores / twelve threads are enough to test
the present concurrency-two Empire deployment, but this does not meet the
owner's earlier desire for development-Mac-like CPU responsiveness. Empire's
technical writer is globally serialized, and the measured V12.6 pilot spent
most of its time in calculation and validation. The reuse decision therefore
depends on the exact P13.7/P13.10 performance gates on `hub-1`; do not raise
worker concurrency merely to use all twelve hardware threads.

Retain the 512 GB SSD for Ubuntu, Docker engine data, images, and code. Mount
the new SSD at the reviewed Empire production data root and place PostgreSQL,
Airflow logs, report/object-store working data, and other durable application
paths there through normal environment/Compose configuration. No Docker
reinstall is required. Before moving data, take and verify a backup; use the
filesystem UUID in `/etc/fstab`, require the mount before containers start,
and rehearse reboot, missing-mount failure, and restore behavior in P13.2-P13.7.
The NAS remains the backup/archive tier, not the live PostgreSQL volume.

### Original HP Versus Framework

Rechecked 2026-09-02: the [original Amazon listing](https://www.amazon.com/dp/B0GVXGLF9X/)
has the selected i7-14700 / 64 GB DDR5 / 2 TB PCIe SSD configuration at
**$2,099**, in stock, shipped and sold by **Poly Molly**. This is an assembled
HP Elite Mini 800 G9, not an HPE server. Ubuntu Server LTS still needs installing
and validating. The listing links to a warranty-information request rather
than establishing HP onsite coverage; support acceptance remains unresolved.

| Comparison | HP Elite Mini 800 G9 | Framework Desktop Max+ 395 |
|---|---|---|
| New 64 GB / 2 TB subtotal, before tax | $2,099 assembled | $2,528 DIY; $2,817 with three-year warranty |
| Case | Approximately 1 L; listing says 6.97 × 6.89 × 1.34 inches | 4.5 L; approximately 3.8 × 8.1 × 8.9 inches |
| Ethernet | 1 GbE | 5 GbE |
| Cinebench R23 single-core | 2,083 | 2,044 |
| Cinebench R23 multicore | 21,831 | 35,226 |

CPU figures come from [CHIP's i7-14700 HP test](https://www.chip.de/test/hp-elite-mini-800-g9-im-test_339296)
and [Notebookcheck's Framework test](https://www.notebookcheck.net/Framework-Desktop-review-Mini-PC-wrapped-in-a-mini-ITX-body.1115803.0.html).
These are different laboratories and memory/storage configurations, not a
controlled comparison of the quoted machines. They indicate similar single-core
speed and roughly 61% more multicore rendering throughput for Framework;
that is not an Empire speedup estimate. CHIP found the HP nearly silent at
idle and audible but restrained at full load, with sustained CPU power limited
by the compact system. Its sone measurements cannot be directly ranked against
Notebookcheck's dB(A) readings.

Framework costs $429 more with its included warranty, or $718 more with the
three-year option; the latter is not a like-for-like support comparison. Its
extra parallel capacity and faster NAS link are useful, but neither establishes
faster serial technical calculations. With inference deferred, the stronger
integrated GPU does not justify a production premium by itself. Prefer HP for
price, size, and assembly convenience; prefer Framework if sustained concurrent
work justifies the additional cost and space. Validate actual Empire throughput
and Ubuntu Server LTS on either selection before promising workload headroom.

### Higher Throughput And Quiet Cooling: Framework Desktop

New US configuration observed on 2026-09-02 in the
[Framework configurator](https://frame.work/products/desktop-diy-amd-aimax300/configuration/new):

| Component | USD |
|---|---:|
| Framework Desktop DIY, Ryzen AI Max+ 395, 64 GB LPDDR5x | 1,959 |
| SANDISK SN7100 PCIe 4.0 M.2 2280, 2 TB | 505 |
| Noctua NF-A12x25 HS-PWM CPU fan | 29 |
| US/CA C13 power cable | 5 |
| Black side panel | Included |
| Three packs of seven black straight front tiles | 30 |
| No Windows license, secondary SSD, handle, or optional front port cards | 0 |
| **Complete DIY subtotal, included one-year warranty** | **2,528** |
| Optional extension to three-year limited warranty | 289 |
| **Complete DIY subtotal with three-year warranty** | **2,817** |

Both totals were verified in the configurator, including the selected
three-year warranty. Tax is excluded. The page advertises free system shipping
and dispatch within five business days, not an arrival date. This is a complete
parts configuration requiring assembly and OS installation, not a factory
Ubuntu installation. Existing rear USB-A/USB-C ports permit setup without the
optional front expansion cards. No cart, account, or order was created.

The [manufacturer specifications](https://frame.work/desktop?slug=desktop-diy-amd-aimax300&tab=specs)
list 16 cores/32 threads, 64 GB soldered memory, two PCIe 4.0 NVMe sockets,
5 GbE, and a 4.5 L enclosure measuring 96.8 × 205.5 × 226.1 mm
(about 3.8 × 8.1 × 8.9 inches). One SSD socket remains free. CPU and RAM require
a mainboard replacement to upgrade. The case, fan, PSU, and SSD are replaceable.
The enclosure is substantially larger than the HP Elite Mini example; treat
size acceptance as unresolved, not automatically within the owner's limit.
The integrated Radeon is incidental to this production choice; AI remains
deferred to a separate host.
Check OS-visible RAM and firmware GPU reservations for this non-inference role
before accepting the 64 GiB planning budget; GPU memory is not additional RAM.

Noise evidence favors this larger cooling design over the reviewed Minisforum
workstations. [Notebookcheck's Framework test](https://www.notebookcheck.net/Framework-Desktop-review-Mini-PC-wrapped-in-a-mini-ITX-body.1115803.0.html)
measured 23.4 dB(A) idle and 36.6–40.1 dB(A) under its load tests at 15 cm,
with a 23.2 dB(A) room floor. That is a different sample/configuration, not a
guarantee for the quoted unit. [Phoronix's Noctua-equipped Linux test](https://www.phoronix.com/review/framework-desktop-power)
also found quiet operation at default settings during extended testing.
Check the actual PSU fan as well as the CPU fan during acceptance.

Performance remains workload-dependent: [Tom's Hardware's 64 GB Framework test](https://www.tomshardware.com/desktops/gaming-pcs/framework-desktop-review)
scored 2,966/17,574 in Geekbench 6, versus 3,880/22,661 for its M4 Pro Mac mini.
That is about 24%/22% lower in that benchmark, although its HandBrake task took
2:43 versus the Mac's 2:47. This supports a capable production candidate, not
a promise that serial Python calculation will match the M4 Pro. Test the actual
Empire path under normal task concurrency; reserve additional capacity for
growth without changing the existing release gates or promising two years of
unmeasured workload capacity.

Ubuntu evidence needs careful qualification. Framework's
[public compatibility matrix](https://frame.work/desktop?tab=linux) currently
lists Ubuntu 25.10 and recommends kernel 6.15 or newer. Its
[26.04 LTS installation guide](https://guides.frame.work/Guide/Ubuntu+26.04+LTS+Installation+on+the+Framework+Desktop/743?lang=en)
uses the Desktop image and is flagged as having no published release. Neither
constitutes verified Ubuntu Server LTS support for Empire. Retain the owner's
Server LTS requirement; verify installer, NIC, NVMe, sensors, reboot/power
recovery, and native Docker in P13.2/P13.7 rather than adopting Ubuntu 25.10.

[Framework warranty service](https://frame.work/warranty) may repair, replace,
or refund an eligible defect at its discretion; onsite service is not assumed.
Its [terms of sale](https://frame.work/terms-of-sale) and
[return help article](https://knowledgebase.frame.work/what-is-the-framework-return-policy-Byhrd6uud)
differ on whether the 30-day window starts at delivery or shipment. Confirm
the applicable return/shipping terms for the order before relying on a trial.

Other evaluated directions:

- **Minisforum MS-A2 / Ryzen 9 9955HX:** stronger CPU capacity, but the
  [reviewed unit](https://www.notebookcheck.com/Minisforum-MS-A2-Kompakter-AMD-Mini-PC-mit-Workstation-Ambitionen-und-GPU-Upgrade-Option-im-Test.1057824.0.html)
  measured about 41.5 dB(A) idle and up to 48.4 dB(A) load at 15 cm. It is not
  the leading recommendation for quiet operation.
- **Minisforum MS-02 Ultra / Core Ultra 9 285HX:** the
  [reviewed unit](https://www.notebookcheck.net/Minisforum-MS-02-Ultra-review-Workstation-as-a-mini-PC-with-Intel-Core-Ultra-PCIe-high-speed-network.1199194.0.html)
  measured 38.2–38.8 dB(A) idle and up to 54.6 dB(A) load at 15 cm. The review
  identifies PSU fan noise and promised improvements, not a verified quiet
  shipping revision. A larger core count does not resolve this purchase risk.
- **ASUS NUC 16 Pro / Core Ultra X7 358H:** a smaller alternative; a
  [firsthand review](https://www.computerbase.de/artikel/pc-systeme/asus-nuc-16-pro-test.98168/)
  found a quiet Whisper profile but substantially louder normal/performance
  profiles. Its Windows-controlled profile behavior must be checked on Ubuntu;
  no complete US 64 GB / 2 TB quote for this exact CPU was established here.
- **Mac mini M5 Pro:** the earlier same-day Apple quote remains a compact
  alternative at $3,499 for 15 CPU cores, 64 GB, and 2 TB (preorder). It requires
  macOS; no M5 Pro Empire benchmark or sustained noise measurement was performed.

## Repository Evidence And Scope

Inspected checkout: `2cd123902c5f76ec6e5ee539d83c8bd0073cc150`; initially clean.
The full active technical plan, its archive and prerequisite Done notes, and
the full design contract were reviewed before edits. Capacity inputs are:

- [V12.8 READY decision](tech-indicators-development-gate-v12.8.md), including
  its reviewed development commit `eedc9d264241e4e6e8b326e21142d31b85c17cf7`.
- [V12.7 audit](tech-indicators-release-candidate-audit-v12.7.md),
  [V12.6 measured performance](tech-indicators-performance-evidence-v12.6.md),
  and [P0.8 release gates](tech-indicators-performance-release-gates-v1.md).
- [Technical design contract](technical-indicators-design-contract.md),
  [OHLCV plan](../todo/ohlcv-plan.md),
  [OHLCV active checklist](../todo/ohlcv-task-plan.md), and
  [OHLCV archived validation notes](../todo/ohlcv-task-plan-archive.md).
- Full source contracts for [EODData](ohlcv-eoddata-source-contract.md),
  [Stooq](ohlcv-stooq-history-source-contract.md), and
  [Yahoo](ohlcv-yahoo-source-contract.md).

The live package configuration still uses 5,000-row default writes, a
10,000-row configurable maximum, and a 25,000-row hard transaction ceiling.
The global advisory lock serializes technical writers; daily calculation
re-evaluates history even when persistence writes only a suffix. CPU sizing
must account for evaluated histories, not just newly written bars.

The [current Compose files](../../deploy/compose/empire.yml) include PostgreSQL,
PgBouncer, five persistent Airflow roles, Redis, and the YouTube POT helper;
Flyway and Airflow initialization are one-off operations. Celery worker
concurrency defaults to two. Jellyfin is an optional profile. This budget
covers the Stonks deployment and normal supporting services. The Ollama
allowance below is historical combined-host planning; substantial media
transcoding, additional VMs, and model training still require separate sizing.
A repository search found no
existing Ollama deployment in `deploy`, `docs`, or `packages` before this update.

Live EODData, Yahoo, and technical DAG definitions all have `schedule=None`.
The archived EODData schedule/unpaused observation is historical. P13.4-P13.5
still own deployment profiles; P13.6 must deploy the exact later reviewed
commit. This procurement record changes no package, database, Core, CLI,
report, environment, or Airflow behavior.

## CPU And Whole-Host Memory

The original eight-core Ryzen 7 proposal was a budget capacity estimate, not a
measured minimum or a match for the development Mac. The revised stronger CPU
candidate and its acoustic/performance tradeoffs are above. Keep effective
single-thread speed, sustained cooling, and concurrency in the comparison.
The V12.6 pilot spent 869.603 seconds calculating and
validating versus 96.207 seconds writing. Extra cores do not remove the single
technical-writer limit. A dedicated GPU is not needed for Stonks calculations;
the future separate AI host needs its own GPU/backend compatibility review.

V12.8 allows at most 2 GiB RSS for a rebuild, 1 GiB for daily processing, and
512 MiB for a report. Those are process limits, not total server requirements.
The following **planning allowances**, in GiB, total 64; they are not current
container limits or proposed PostgreSQL settings.

| Consumer | GiB |
|---|---:|
| OS, Docker daemon, monitoring | 4 |
| Airflow API, scheduler, DAG processor, triggerer, worker parent | 8 |
| Two task processes, including one technical rebuild | 4 |
| PostgreSQL total allowance, including connections and maintenance | 8 |
| Redis, PgBouncer, helper service | 2 |
| Backup, image builds, and operational maintenance allowance | 6 |
| Filesystem cache | 16 |
| Unallocated operating headroom | 16 |
| **Total** | **64** |

Retain the documented concurrency and database defaults initially; tune only
against measured production plans and memory. In particular, an 8 GiB database
allowance does not mean setting `shared_buffers` to 8 GiB. P13.7 must measure
the simultaneous workload, memory pressure, temperatures, and sustained CPU
behavior. Budget machines use consumer memory/support; no ECC, BMC, hot-swap,
or onsite repair capability is assumed.

### CPU Comparison With The Owner's Development Mac

On 2026-09-02, a read-only `system_profiler SPHardwareDataType` query identified
the current laptop as MacBook Pro `Mac16,7`, Apple M4 Pro, 14 CPU cores
(10 performance and four efficiency), and 48 GB RAM. Serial numbers and other
device identifiers were excluded from the captured output. No benchmark was
run on the laptop for this comparison.

Published Geekbench 6 submissions give directional evidence:

| Published system / submission | Single core | Multi core |
|---|---:|---:|
| [M4 Pro 14-core, 48 GB, macOS, Geekbench 6.3](https://browser.geekbench.com/v6/cpu/9593981) | 3,975 | 22,971 |
| [AI X1 Ryzen 7 255, 32 GB, Windows, Geekbench 6.4](https://browser.geekbench.com/v6/cpu/13448746) | 2,627 | 13,529 |
| [AI X1 Ryzen 7 255, 16 GB, Windows, Geekbench 6.4](https://browser.geekbench.com/v6/cpu/12804195) | 2,570 | 11,651 |

These are other users' submissions, not population averages or controlled
Empire tests. The Ryzen examples score about 34–35% lower in single-core and
41–49% lower in multi-core work than the cited matching Mac configuration.
Different OS, benchmark minor versions, RAM, power limits, and cooling affect
results; those percentages must not be applied as exact Empire runtime ratios.

Engineering assessment: the AI X1 may meet the existing production gates, but
CPU-heavy calculation, validation, and builds can take noticeably longer than
on the M4 Pro. Routine administration and light queries may still respond well.
Core count alone does not establish comparable performance, and 64 GB RAM does
not compensate for slower CPU execution when neither machine is memory-bound.
If comparable laptop CPU performance is a purchase requirement, compare faster
CPU candidates and validate the actual Empire workload before endorsing a
model. Do not present the Ryzen 7 255 as meeting that requirement based solely
on its eight cores or the development pilot's margin over minimum gates.

## Deferred AI Host And Historical Combined Capacity

The latest split-host proposal defers this purchase. The following 128 GiB
budget describes the earlier combined machine only; it must not be copied as
the dedicated AI host's minimum, since that machine would not run Empire's
64 GiB allocation. Re-size it for the selected model and concurrency later.

More RAM increases the models and contexts that can fit, but GPU support,
memory bandwidth, model architecture, quantization, and request concurrency
also determine usefulness. An ordinary 128 GB DDR5 mini PC does not imply
128 GB of fast GPU memory. Conversely, a smaller model can run with far less
than 128 GB: Ollama's [Qwen3 8B Q4_K_M](https://ollama.com/library/qwen3:8b)
download is 5.2 GB, and [Qwen3 32B Q4_K_M](https://ollama.com/library/qwen3:32b)
is 20 GB. These are sizing examples, not runtime-memory measurements or a
selection of the best model for Empire's tasks.

For initial planning, assume one resident quantized model, one active request,
and an explicit 8,192-token context. Begin evaluation with an 8B–32B class
model for bounded extraction, summarization, or coding assistance. Weights,
KV cache, compute buffers, and server overhead must all fit; download size
alone is insufficient. Ollama documents that context length and parallel
requests increase memory demand in its [FAQ](https://docs.ollama.com/faq).
Propose `OLLAMA_MAX_LOADED_MODELS=1` and `OLLAMA_NUM_PARALLEL=1` for the future
runtime, with the context explicitly bounded. These are planning settings,
not changes to the committed environment or guarantees about a particular model.

| Combined planning allowance | GiB |
|---|---:|
| Existing Empire budget above, including cache and its reserve | 64 |
| Ollama weights, KV cache, buffers, and runtime allowance | 48 |
| Additional shared CPU/GPU/driver operating headroom | 16 |
| **Total installed-memory target** | **128** |

On a unified-memory system these allowances share one physical pool. Do not
count GPU memory again as extra RAM, or dedicate 96 GB to the GPU while also
assuming 64 GB remains for Empire. Budget firmware reservations inside the
same total and verify actual usable memory. Larger models or longer contexts
need a new measured allocation; loading a model successfully does not prove
acceptable response latency or task accuracy.

[Ollama's current Linux hardware support](https://docs.ollama.com/gpu) lists
Ryzen AI Max+ 395 and requires a suitable ROCm 7 driver stack for that backend.
Its [Docker instructions](https://docs.ollama.com/docker) document the ROCm
image and GPU-device access, plus a Vulkan alternative. Favor a supported
Linux GPU path and verify the actual installed versions. NPU marketing TOPS
are not an Ollama throughput estimate. This proposal adds no alternative OS,
GPU overrides, container, model download, or task-routing implementation.

Future AI acceptance must include `ollama ps` and runtime logs proving the intended
GPU offload, repeatable output checks on representative tasks, first-token and
generation latency, peak memory, sustained thermals, and Empire's existing
daily/query/report gates while integration runs. Prove that disconnecting or
restarting the AI host does not interrupt existing non-AI production workflows.
Stop or unload inference if its gates fail. Select and pin the eventual
model/quantization after that evaluation; no tokens-per-second figure is
claimed before hardware testing.

## Storage Growth, Database, And NAS

The development baseline is 22,261 eligible listings and 20,584,282 source
rows, across the seven exact V12.8 cohorts. It is not a current production
inventory. Recount before every cohort. Preserve provider-native histories;
do not deduplicate EODData and Stooq to reduce the capacity estimate.

| Projection | Calculation | Result |
|---|---|---:|
| Initial two technical slots, including measured indexes | `20,584,282 * 935.5264 * 2 / 2^30` | 35.869 GiB |
| Annual added observations, fixed-universe scenario | `22,261 * 252` | 5,609,772 rows |
| Annual two-slot technical growth | `5,609,772 * 935.5264 * 2 / 2^30` | 9.775 GiB |
| Two slots after five years in that scenario | `(20,584,282 + 5 * 5,609,772) * 935.5264 * 2 / 2^30` | 84.746 GiB |
| WAL for one initial write pass, pilot ratio | `20,584,282 * 1,222,512,408 / 1,000,000 / 2^30` | 23.436 GiB |
| Initial minimum free-space gate | `87,765,975,184 / 2^30` | 81.738 GiB |

The annual scenario assumes 252 additional observations for every listing;
listings, historical backfills, corrections, and source coverage can grow
faster. The P0.8 source table was about 5.29 GiB including indexes. This is
only one relation, not the whole database. WAL is write churn, not retained
table growth; retries, corrections, checkpoints, and other services add to it.

The revised target is **2 TB local NVMe SSD** (1,862.645 GiB before formatting),
providing fast local database and scratch storage while the NAS retains durable
objects and backups. A rotating hard drive is not proposed for this role.

| Local disk planning allocation | GiB |
|---|---:|
| OS, images, and logs | 100 |
| Database relations and growth | 250 |
| WAL and transient database work | 150 |
| Import, build, and application scratch | 100 |
| Additional Empire data, image, and staging headroom | 400 |
| Free generation/maintenance reserve | 400 |
| **Budgeted total** | **1,400** |
| **Additional unallocated capacity before formatting** | **462.645** |

These are monitoring budgets, not partitions. The 400 GiB previously reserved
for models stays available to Empire; no model store is planned on this host.
The future AI host should budget its own local models and download staging.
NAS offload does not reduce model runtime RAM needs.
The actual pre-generation free-space formula remains mandatory as history
grows. Stop before a cohort whose projected headroom exceeds available space.

Proposed storage placement: local NVMe for `EMPIRE_POSTGRES_DATA_DIR` and
`EMPIRE_TEMP_DIR`; NAS-backed durable Core storage and separate database
backups. Keep existing Core roots, object keys, and absolute mount conventions.
Do not initialize roots before P13.3 proves the intended NAS mounts. Database
placement is a proposal for the later deployment, not an environment edit.

Reserve **at least 1 TiB usable NAS capacity for Empire initially**, subject to
an inventory of existing data and the P13.7 backup design. Budget two complete
database backup generations, retained WAL, raw imports, source artifacts,
reports, and growth separately. Stooq's 4 GiB compressed archive ceiling can
consume space both locally and in Core; selected members are streamed rather
than fully extracted. A technical report pair is bounded at 7 MiB; ten pairs
per day would add about 25 GiB/year. That illustrative rate is not a schedule
or retention policy and excludes OHLCV and other reports. Durable reports are
not disposable scratch; no purge policy is introduced here.

## Network, Power, And Acceptance Handoff

Use wired Ethernet. 2.5 GbE is preferred for NAS transfers; existing 1 GbE may
be adequate if P13.3 measures acceptable backup/restore and source-transfer
times. A 100 GiB transfer has a wire-rate floor of about 14.3 minutes at 1 Gb/s
or 5.7 minutes at 2.5 Gb/s, before protocol/disk overhead. A 2.5 GbE host port
does not establish the speed of the switch or NAS. NAS, switch, cabling, UPS,
and available usable storage have not been inventoried or priced.

Use the supplied power adapter and budget UPS coverage for the host, NAS, and
network equipment together. P13.2 owns firmware, Ubuntu Server LTS, Docker,
automatic restart after power loss, cooling, and recovery access. Consumer
NVMe is not assumed to provide power-loss protection; P13.7 owns backup and
restore verification. Buying a second SSD alone is not a backup strategy.

Choose and record the exact Ubuntu LTS release/kernel in P13.2 after checking
the purchased hardware. As of 2026-09-02,
[Docker's Ubuntu support](https://docs.docker.com/engine/install/ubuntu/)
includes 24.04 and 26.04 LTS on amd64. This does not certify a particular mini
PC. The inspected GMKtec M5 Ultra and Minisforum AI X1 listings did not establish
exact Ubuntu Server LTS certification/support. Verify installer boot, wired
NICs, NVMe, sensors/fan behavior, firmware updates, and unattended restart on
the selected device. For a later non-Mac AI host, verify its GPU driver/Ollama
backend supports the chosen Ubuntu LTS; a vendor-supplied OS is not sufficient
evidence that Ubuntu Server is supported.

P13.7 and P13.10 must re-prove the existing gates on the purchased host:
at least 250 evaluated-and-persisted rows/second, initial rebuild under
24 hours, bounded daily append/correction under five minutes, transaction
target 30 seconds/hard maximum 60 seconds, process RSS and query/report
limits, and generation free space. Include RAM testing and SSD health/endurance
inspection during host acceptance. No broad laptop backfill is authorized.

## Dated New-Hardware Quotes

USD observations on 2026-09-02; prices exclude tax, any destination-dependent
shipping/duties, and unrelated infrastructure. No coupon, membership discount,
trade-in, or RAM resale credit is assumed. Listings can change selected CPU,
memory, and seller: the exact options below are part of the quote.

| Candidate | Complete configuration and observed subtotal | Expansion / limitation |
|---|---|---|
| [GMKtec M5 Ultra RAM replacement](https://www.gmktec.com/products/gmktec-nucbox-m5-ultra-amd-ryzen-7-7730u-ryzen-3-5400u-mini-pc?variant=47330098020506) | R7 7730U, US plug, 16 GB/512 GB at $449.99; replace RAM with the $315 kit below: **$764.99** | 64 GB maximum; two M.2 2280 slots; dual 2.5 GbE; 128.8 × 127 × 47.8 mm |
| [GMKtec M5 Ultra barebones](https://www.gmktec.com/products/gmktec-nucbox-m5-ultra-amd-ryzen-7-7730u-ryzen-3-5400u-mini-pc?variant=47330097889434) | R7 7730U, US plug, $329.99 + $315 RAM + $153.99 Newegg-sold 1 TB SSD: **$798.98** | Original Empire-only budget build; one SSD slot remains free; assembly required; below revised RAM/storage target |
| [Minisforum AI X1](https://store.minisforum.com/products/minisforum-ai-x1-mini-pc?variant=46484012892405) | Ryzen 7 255, 64 GB/1 TB, US, SKU `X1-25561US`: **$1,159**; live catalog available | Two SO-DIMMs, published maximum 64 GB for this CPU variant; two M.2 slots; 2.5 GbE |
| [HP example supplied by owner](https://www.amazon.com/dp/B0GVXGLF9X/) | Elite Mini 800 G9, i7-14700, selected 64 GB DDR5/2 TB: **$2,099**, in stock | More storage and a different CPU; exact reseller upgrade warranty and expansion limit not verified |

Budget RAM: [Rimlance RSO25600D8C2K64](https://www.newegg.com/rimlance-64gb-260-pin-ddr4-so-dimm/p/0RM-00GJ-000A6),
2 × 32 GB DDR4-3200, 1.2 V, non-ECC unbuffered SO-DIMMs, **$315**.
The product page identifies **Focus Memory**, shipping from China. It lists
30-day refund/replacement returns but directs warranty questions to the seller.
The catalog advertises free shipping; the final destination quote is pending.
Electrical/form-factor specifications match the M5's documented memory type;
this is not a verified motherboard/BIOS compatibility-list entry. The unclear
warranty and untested kit are unresolved purchase tradeoffs, not a guarantee.

Budget SSD: [Team Group MP33 1 TB, TM8FP6001T0C101](https://www.newegg.com/team-group-1tb-mp33-nvme-1-3/p/N82E16820331417),
M.2 2280 PCIe 3.0 NVMe. The **Newegg-sold $153.99** offer includes free shipping
from the US. A separate Hot Deals 4 Less offer was $139.99 before delivery
costs, giving a lower **$784.98** parts subtotal if its delivered terms are
acceptable. The page advertises a five-year limited warranty, but conflicting
240/600 TBW figures; confirm exact revision/endurance and warranty eligibility
before ordering. Neither offer is an enterprise SSD or a measured DB result.

The [GMKtec M6 Ultra](https://www.gmktec.com/products/amd-ryzen-5-7640hs-mini-pc-nucbox-m6-ultra)
US barebones was **$269.99**, SKU `M6 ULTRA-0-00S`; the manufacturer specifies
Ryzen 5 7640HS and up to 128 GB across two DDR5 SO-DIMMs. A fresh 64 GB / 2 TB
Empire-only quote could compare its six-core CPU against the proposed
eight-core candidates; extra RAM capacity alone does not establish equivalent
CPU or Ollama performance. No complete cost or kit compatibility was established.
The K12 live catalog offered only
barebones/32 GB despite an indexed 64 GB option. Beelink SER8 offered
16/32 GB preorders. Neither was counted as a priced 64 GB assembled alternative.

### Deferred AI Comparisons, 128 GB / 2 TB

All four are new complete systems with Ryzen AI Max+ 395 and Radeon 8060S;
the quoted prices include RAM and SSD. USD observations on 2026-09-02 exclude
sales tax and any destination exceptions. The 128 GB LPDDR5X is onboard,
not an upgradeable SO-DIMM kit. These were quoted for the earlier combined-host
proposal. Re-quote and re-size for a separate AI host when its workload is known.

| Host and exact selection | Price | Availability / support comparison |
|---|---:|---|
| [BOSGAME M5 AI](https://www.bosgamepc.com/products/bosgame-m5-ai-mini-desktop-ryzen-ai-max-395?sku=18070578044354691493644095), `M5 395_128G+2TB`, US | **$2,999.00** | Selected live page permits ordering; US warehouse and free shipping advertised; one-year warranty |
| [GMKtec EVO-X2](https://www.gmktec.com/en/products/amd-ryzen%E2%84%A2-ai-max-395-evo-x2-ai-mini-pc?variant=46826048585882), 128 GB/2 TB, US, `EVO-X2-5-75S` | **$3,649.99** | Live catalog available; one-year warranty; policy delivery window below |
| [Minisforum MS-S1 Max](https://store.minisforum.com/products/minisforum-ms-s1-max-mini-pc?variant=47071388139765), 128 GB/2 TB, US, `MS-S1-MAX12US` | **$3,799.00** | Live option explicitly estimates mid-September shipping; two-year direct-store warranty; shipping date is not arrival date |
| [Beelink GTR9 Pro](https://www.bee-link.com/products/beelink-gtr9-pro-amd-ryzen-ai-max-395), 128 GB/2 TB, Frost Silver, US | **$4,349.00** | Product page says presale, ships within 35 days; three-year warranty advertised |

The BOSGAME has a 16-core/32-thread CPU, 128 GB LPDDR5X-8000 shared memory,
two M.2 PCIe 4.0 slots, and 2.5 GbE. RAM expansion ends at the purchased
capacity. Verify the supplied SSD layout, exact drive/endurance, physical
clearance, and firmware-supported memory allocation during purchase/acceptance;
the listing is not evidence of Empire-tested thermals or inference performance.
The price advantage over the EVO-X2 is $650.99. These comparisons do not claim
an exhaustive lowest market price or equivalence to a dedicated NVIDIA GPU.

## Support, Delivery, And Purchase Decision

[BOSGAME's return/warranty policy](https://www.bosgamepc.com/pages/return-exchange-policy)
provides one year from receipt and a 30-day return/exchange request window;
non-quality returns incur a stated 5% fee. Support is through the seller's
service process, not an onsite SLA. Its
[shipping policy](https://www.bosgamepc.com/policies/shipping-policy) advertises
free shipping, dispatch within 48 hours on business days, and an estimated
7–12-day delivery window. The selected M5 page states US-warehouse fulfillment
without import fees. Confirm stock, destination, taxes, and arrival at ordering;
no order-specific delivery date is established by these policy statements.

[GMKtec's warranty](https://www.gmktec.com/pages/warranty-returns-refund)
is one year from order, with email/mail-in service; its policy has a seven-day
return window and a 15% restocking deduction for opened non-quality returns.
RAM and separately bought storage have their own seller/manufacturer coverage.
[GMKtec shipping](https://www.gmktec.com/pages/shipping-policy-track-your-order)
quotes 1–3 business days processing plus 1–2 weeks to the US, or 3–5 days from
US stock. This is a policy estimate, not a confirmed warehouse or arrival date.
The complete build's arrival depends on the RAM shipment as well.

[Minisforum's direct-store policy](https://store.minisforum.com/policies/refund-policy)
provides two years for purchases from August 1, 2026, with eligible US service
center repair and a 30-day return window. The earlier three-year promotion
does not apply. [Shipping terms](https://store.minisforum.com/policies/shipping-policy)
depend on warehouse allocation; processing is generally 1–3 business days
and can lengthen during promotions. The policy also describes much longer
cross-border transit. An address-specific warehouse and arrival quote is
required; free shipping does not establish a delivered tax/duty total.

The HP Amazon page displayed September 8 standard delivery and September 4
with Prime for its default displayed delivery area. That was not a user-supplied
destination and is not a promised delivery date for this purchase.

| Decision field | Current record |
|---|---|
| Owner-approved constraints | New only; compact and quiet; 64 GB RAM / 2 TB SSD; stronger CPU and responsiveness with 12–24 months planning headroom; lowest practical price within those priorities; HPE optional; Ubuntu Server LTS for every non-macOS device |
| Selected production host | Reuse the confirmed HP Elite Mini 805 G8 `hub-1` for approximately one year; defer a separate AI host and retain the $2,099 replacement HP and $2,528 Framework only as fallbacks |
| Owner-reviewed final selection | PNY `MN64GK2D43200-TB` 64 GB matched SODIMM kit plus WD_BLACK SN7100 `WDS200T4X0E` 2 TB NVMe SSD; retain the healthy 512 GB boot SSD |
| Warranty/support acceptance | Consumer support accepted: PNY published limited lifetime memory coverage and Sandisk five-year/1,200-TBW SSD coverage, both subject to purchase and claim terms; no onsite SLA |
| Ordered-price record | $721.98 planning subtotal before tax from the observed selected offers; the private order confirmation governs the actual charge |
| Purchase decision / order | Approved and ordered by the owner on 2026-09-04 |
| Expected delivery | Amazon order shows arrival 2026-09-05; installation and observed delivery are P13.2 evidence |
| Expansion headroom | RAM reaches the documented 64 GB maximum; both M.2 positions will be occupied after installation; NAS/external storage or drive replacement supplies later capacity |
| P13.1 completion | Complete; selection, purchase decision, support tradeoff, expansion limit, and expected delivery are recorded. Hardware fit, burn-in, and production readiness remain later gates |

## Verification

This is a documentation/procurement task. Package metadata/README, live
configuration, Compose topology, source DAGs, and prerequisite evidence were
inspected. Manufacturer live catalog variants and retailer product pages were
checked for the exact quoted combinations; stale search-result prices and
unavailable configurations were excluded from complete-price comparisons.

Repository verification passed: `git diff --check` and
`git diff --no-index --check /dev/null docs/stonks/tech-indicators-production-host-p13.1.md`;
a `python3` standard-library check passed for two Markdown files, all 15
relative links, balanced code fences, P13.1 unchecked state, quote totals,
memory/storage sums, and growth calculations.
The Ollama extension rechecks those links and calculations, the 128 GiB
combined allowance, 2 TB/1,400 GiB disk budget, four exact AI configurations,
and the $650.99 comparison. Current official Ollama hardware, Docker, memory,
and model-size documentation was reviewed. No model was downloaded or executed.
No runtime code changed, so package tests, DB validation, imports, report
rendering, CLI and Airflow smokes were not rerun. Production hardware checks
remain unrun until the host is obtained and the later gates authorize them.

Split-host revision (2026-09-02): verified with `git diff --check` and an inline
`python3` standard-library check of both Markdown files for relative-link
targets, balanced code fences, trailing whitespace, P13.1 unchecked state,
Ubuntu/split-host scope, and the 64 GiB / 1,400 GiB planning table totals.
Docker's official Ubuntu compatibility and the two budget vendor listings were
reviewed; hardware Ubuntu compatibility remains unverified. No new price quote,
runtime deployment, or model execution was performed by this revision.

Stronger-CPU revision (2026-09-02): read-only live Framework configuration
verified the selected CPU/RAM, 2 TB SSD, Noctua fan, US cable, full tile set,
$2,528 subtotal, and $2,817 with selected three-year warranty. `git diff --check`
and an inline `python3` standard-library check passed for both Markdown files,
15 relative-link targets, balanced fences, trailing whitespace, P13.1 unchecked
state, the component/warranty totals, the 64 GiB and 1,400 GiB budgets, and CPU
comparison arithmetic. Reviewed current manufacturer OS/support material and
firsthand acoustic/CPU tests. No hardware, runtime, DB, CLI, or Airflow tests
were run; the revised procurement proposal is not a production gate result.

HP comparison revision (2026-09-02): rechecked the live selected Amazon variant,
price, availability, seller, and warranty-information link. Reviewed firsthand
tests of the non-T i7-14700 HP and Framework. `git diff --check` and an inline
`python3` check passed for relative links, fences, whitespace, unchecked P13.1,
the $429/$718 differences, and the 61% multicore comparison. Hardware performance
and Ubuntu Server LTS remain untested; no runtime changes were made.

Existing-host revision (2026-09-04): reviewed the related Codex hardware record,
HP G8 platform specification, AMD CPU interface, Sandisk endurance contract,
and both live selected Amazon offers. `git diff --check` and an inline `python3`
check passed for relative links, fences, whitespace, unchecked P13.1, the
$777.99 subtotal, and the $1,321.01 replacement-price difference. Physical slot
inspection and all production performance, storage, reboot, and restore checks
remain unrun. No part was purchased and no runtime was changed.

Live `hub-1` inventory revision (2026-09-04): confirmed the exact HP Elite Mini
805 G8 model, Ubuntu/kernel, CPU topology, BIOS, one-module memory layout,
single visible NVMe device, filesystem capacity, Docker baseline, and filtered
boot-SSD health. The BIOS matches HP's published 02.17.00 security-remediation
minimum. Documentation checks below were rerun; no firmware, storage, Docker,
or purchase action was performed.

Memory-vendor revision (2026-09-04): compared new exact-spec 64 GB kits from
Timetec's Amazon seller, authorized Crucial resellers Provantage and B&H, and
OWC direct. The $400.99 Timetec 2Rx8 kit is the current value recommendation;
with the linked SSD the subtotal is $710.98. Prices exclude tax and remain
purchase-time checks. No cart or order was created.

Purchase revision (2026-09-04): recorded the owner-confirmed order for PNY
`MN64GK2D43200-TB` 64 GB memory and WD_BLACK SN7100 `WDS200T4X0E` 2 TB NVMe,
expected 2026-09-05, with a $721.98 observed-offer planning subtotal before
tax. Rechecked the exact PNY product specification and published limited
lifetime memory warranty plus the Sandisk five-year/1,200-TBW SSD terms.
Focused Markdown assertions and `git diff --check` passed. Installation,
hardware health, storage, reboot, restore, and production performance remain
P13.2-P13.10 acceptance work.
