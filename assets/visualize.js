(function () {
	"use strict";

	const CATEGORY_COLORS = {
		1: "#3ddc84",
		2: "#ffd24f",
		3: "#ff9f43",
		4: "#ff5d5d",
		5: "#b06bff",
	};
	const DEFAULT_CATEGORY_COLOR = "#8892a6";

	const AREA_STYLE = {
		tcWindArea: {
			color: "#8892a6",
			fillColor: "#8892a6",
			fillOpacity: 0.12,
			weight: 1.5,
			layerKey: "windArea",
		},
		tcForecastArea: {
			color: "#b06bff",
			fillColor: "#b06bff",
			fillOpacity: 0.08,
			weight: 1.5,
			layerKey: "forecastArea",
		},
		tcWarningArea: {
			color: "#ff7a00",
			fillColor: "#ff7a00",
			fillOpacity: 0.12,
			weight: 1.5,
			layerKey: "warningArea",
		},
		tcWatchArea: {
			color: "#ffe14f",
			fillColor: "#ffe14f",
			fillOpacity: 0.1,
			weight: 1.5,
			layerKey: "watchArea",
		},
	};
	const WIND_AREA_COLORS = { Current: "#ff5d5d", Forecast: "#4fa8ff" };

	// Best-track wind areas: gale / storm / hurricane force, drawn from the
	// interpolated quadrant radii. Colours are kept apart from the bulletin
	// area colours above: a pink-to-magenta ramp (no other layer uses pink) with
	// dashed outlines, so they can't be mistaken for the solid bulletin areas.
	const BEST_TRACK_AREA_STYLE = {
		GF: {
			label: "Gale force (34 kn)",
			color: "#ff9ee0",
			fillOpacity: 0.1,
			layerKey: "btGale",
		},
		SF: {
			label: "Storm force (48 kn)",
			color: "#ff3fb4",
			fillOpacity: 0.16,
			layerKey: "btStorm",
		},
		HF: {
			label: "Hurricane force (64 kn)",
			color: "#c4007a",
			fillOpacity: 0.24,
			layerKey: "btHurricane",
		},
	};

	// Observed gale area over a window after the bulletin's base time, set by the
	// From / To inputs (default 0-48 h: from the bulletin base time to the end of
	// the Watch range gen_cont_tables.py scores Table C against).
	const GALE_WINDOW = { color: "#3ddc84", fillOpacity: 0.14 };
	const GALE_WINDOW_MAX_H = 60;

	const els = {
		cyclone: document.getElementById("cycloneSelect"),
		slider: document.getElementById("bulletinSlider"),
		label: document.getElementById("bulletinLabel"),
		prev: document.getElementById("prevBtn"),
		next: document.getElementById("nextBtn"),
		play: document.getElementById("playBtn"),
		info: document.getElementById("info"),
		status: document.getElementById("status"),
		uploadStatus: document.getElementById("uploadStatus"),
		uploadGmlBtn: document.getElementById("uploadGmlBtn"),
		refreshBestTrackBtn: document.getElementById("refreshBestTrackBtn"),
		gmlUploadInput: document.getElementById("gmlUploadInput"),
		categoryLegend: document.getElementById("categoryLegend"),
		// Towns are static, so this checkbox is deliberately kept out of
		// els.layers -- everything in there is wired to renderBulletin().
		towns: document.getElementById("layer-towns"),
		townsNote: document.getElementById("townsNote"),
		layers: {
			tracks: document.getElementById("layer-tracks"),
			fixes: document.getElementById("layer-fixes"),
			windArea: document.getElementById("layer-windArea"),
			forecastArea: document.getElementById("layer-forecastArea"),
			warningArea: document.getElementById("layer-warningArea"),
			watchArea: document.getElementById("layer-watchArea"),
			allBulletins: document.getElementById("layer-allBulletins"),
			bestTrack: document.getElementById("layer-bestTrack"),
			btGale: document.getElementById("layer-btGale"),
			btStorm: document.getElementById("layer-btStorm"),
			btHurricane: document.getElementById("layer-btHurricane"),
			btGaleWindow: document.getElementById("layer-btGaleWindow"),
		},
		// Outside els.layers: these are numbers, not checkboxes.
		galeFrom: document.getElementById("galeFrom"),
		galeTo: document.getElementById("galeTo"),
		compareToggle: document.getElementById("compareToggle"),
		comparePanel: document.getElementById("comparePanel"),
		compareClose: document.getElementById("compareClose"),
		compareSelectors: document.getElementById("compareSelectors"),
		addCompareCyclone: document.getElementById("addCompareCyclone"),
		compareStatus: document.getElementById("compareStatus"),
		compareLevels: {
			GF: document.getElementById("compare-gale"),
			SF: document.getElementById("compare-storm"),
			HF: document.getElementById("compare-hurricane"),
		},
		compareTimeBar: document.getElementById("compareTimeBar"),
		compareSlider: document.getElementById("compareSlider"),
		compareTimeLabel: document.getElementById("compareTimeLabel"),
		comparePrev: document.getElementById("comparePrevBtn"),
		compareNext: document.getElementById("compareNextBtn"),
	};

	Object.entries(CATEGORY_COLORS).forEach(([cat, color]) => {
		const chip = document.createElement("span");
		chip.className = "legend-chip";
		chip.innerHTML = `<span class="swatch" style="background:${color}"></span>Cat ${cat}`;
		els.categoryLegend.appendChild(chip);
	});

	const map = L.map("map", {
		maxZoom: 9,
		minZoom: 3,
		maxBounds: [
			[-90, -100],
			[90, 260],
		],
	}).setView([-20, 133], 4);

	// Town dots need their own pane above Leaflet's overlayPane (400), or they
	// vanish under the translucent wind/warning/watch polygons.
	map.createPane("towns");
	map.getPane("towns").style.zIndex = 450;

	// CARTO watermarks raster tiles requested without an API key. The key lives
	// in a git-ignored .env and is baked into data/map_config.json by
	// build_map_config.py -- a static page can't read .env itself. A missing or
	// unreadable config falls back to the keyless URL, so the map still works
	// for anyone who hasn't run that script.
	const DEFAULT_BASEMAP = {
		basemapUrl:
			"https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
		attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
		subdomains: "abcd",
		maxZoom: 19,
	};

	async function initBasemap() {
		let cfg = DEFAULT_BASEMAP;
		try {
			const res = await fetch("data/map_config.json");
			if (res.ok) cfg = { ...DEFAULT_BASEMAP, ...(await res.json()) };
		} catch (err) {
			// Keep the keyless default.
		}
		L.tileLayer(cfg.basemapUrl, {
			attribution: cfg.attribution,
			subdomains: cfg.subdomains,
			maxZoom: cfg.maxZoom,
		}).addTo(map);
	}

	const bulletinLayer = L.layerGroup().addTo(map);
	const ghostLayer = L.layerGroup().addTo(map);
	const bestTrackLayer = L.layerGroup().addTo(map);
	const comparisonLayer = L.layerGroup().addTo(map);
	const compareAreaLayer = L.layerGroup().addTo(map);
	const townsLayer = L.layerGroup().addTo(map);

	let index = null;
	let cyclonesById = new Map();
	let currentBulletins = [];
	let currentBestTrack = null;
	let galeWindowNote = "";
	let currentIdx = 0;
	let playTimer = null;
	let towns = [];
	let comparisonMode = false;
	let compareSelections = [];
	let compareTracks = [];
	const COMPARE_COLORS = [
		"#2fd4d9",
		"#ff9f43",
		"#b06bff",
		"#3ddc84",
		"#ff5d5d",
	];

	const sidebar = document.getElementById("sidebar");
	const optionsToggle = document.getElementById("optionsToggle");
	const verificationTab = document.getElementById("verificationTab");

	function setSidebarOpen(isOpen) {
		sidebar.hidden = !isOpen;
		optionsToggle.setAttribute("aria-expanded", String(isOpen));
		optionsToggle.innerHTML = isOpen
			? 'Visualizer Options <span aria-hidden="true">◀</span>'
			: 'Visualizer Options <span aria-hidden="true">▶</span>';
		requestAnimationFrame(() => map.invalidateSize());
	}

	function openVerificationTab() {
		const bulletin = currentBulletins[currentIdx];
		localStorage.setItem(
			"cycloneVerification",
			JSON.stringify({
				distId: bulletin?.distId || els.cyclone.value,
				distName: bulletin?.distName,
				bulletin: bulletin
					? `${currentIdx + 1}/${currentBulletins.length} — ${fmtTime(bulletin.fcastTime)}`
					: null,
			}),
		);
		window.location.href = "verification.html";
	}

	optionsToggle.addEventListener("click", () =>
		setSidebarOpen(sidebar.hidden),
	);
	verificationTab.addEventListener("click", openVerificationTab);
	els.compareToggle.addEventListener("click", () => {
		if (comparisonMode) closeComparison();
		else openComparison();
	});
	els.compareClose.addEventListener("click", closeComparison);
	els.addCompareCyclone.addEventListener("click", () => {
		if (compareSelections.length < 5) {
			compareSelections.push("");
			renderCompareSelectors();
		}
	});
	Object.values(els.compareLevels).forEach((box) =>
		box.addEventListener("change", () => updateCompareSlider(false)),
	);
	els.compareSlider.addEventListener("input", () => drawCompareAreas());
	els.comparePrev.addEventListener("click", () => stepCompareSlider(-1));
	els.compareNext.addEventListener("click", () => stepCompareSlider(1));
	setSidebarOpen(true);

	function stepCompareSlider(direction) {
		const slider = els.compareSlider;
		const step = 1;
		slider.value = Math.min(
			Number(slider.max),
			Math.max(0, Number(slider.value) + direction * step),
		);
		drawCompareAreas();
	}

	function setStatus(msg, isError) {
		els.status.textContent = msg || "";
		els.status.className = isError ? "error" : "";
	}

	function setUploadStatus(msg, isError) {
		els.uploadStatus.textContent = msg || "";
		els.uploadStatus.className = isError
			? "upload-status error"
			: "upload-status";
	}

	async function uploadDataset(file, endpoint, label) {
		if (!file && endpoint !== "refresh-best-track") return;
		const formData = file ? new FormData() : null;
		if (file) formData.append("file", file);
		setUploadStatus(
			file
				? `Uploading ${label}…`
				: `Requesting current ${label} from BOM…`,
		);
		try {
			const response = await fetch(`${API_BASE}/datasets/${endpoint}`, {
				method: "POST",
				body: formData,
			});
			const payload = await response.json().catch(() => ({}));
			if (!response.ok) {
				throw new Error(payload.detail || `Failed to upload ${label}.`);
			}
			if (!payload.job_id)
				throw new Error("The server did not return an upload job ID.");
			let offset = 0;
			const deadline = Date.now() + 30 * 60 * 1000;
			while (Date.now() < deadline) {
				const jobResponse = await fetch(
					`${API_BASE}/datasets/jobs/${encodeURIComponent(payload.job_id)}?since=${offset}`,
				);
				if (jobResponse.status === 404)
					throw new Error(
						"The upload job is no longer available; the server may have restarted.",
					);
				const job = await jobResponse.json().catch(() => ({}));
				if (!jobResponse.ok)
					throw new Error(
						job.detail ||
							`Could not read ${label} processing status.`,
					);
				offset = job.next || offset;
				const lastMessage =
					job.messages && job.messages.length
						? job.messages[job.messages.length - 1]
						: `Processing ${label}…`;
				setUploadStatus(lastMessage);
				if (job.status === "completed") {
					setUploadStatus(
						job.result?.interpolation_error
							? `${label} uploaded; interpolation warning: ${job.result.interpolation_error}`
							: `${label} uploaded and processed successfully.`,
					);
					break;
				}
				if (job.status === "failed")
					throw new Error(job.error || `${label} processing failed.`);
				await new Promise((resolve) => setTimeout(resolve, 650));
			}
			if (Date.now() >= deadline)
				throw new Error(
					`${label} processing exceeded the 30-minute limit.`,
				);
			if (endpoint === "upload") {
				await loadIndex();
			}
			if (endpoint === "refresh-best-track") {
				await loadCyclone();
			}
		} catch (err) {
			setUploadStatus(err.message || `Could not upload ${label}.`, true);
			throw err;
		}
	}

	function toLatLngs(coords) {
		return coords.map(([lon, lat]) => [lat, lon]);
	}

	function categoryColor(cat) {
		if (!cat) return DEFAULT_CATEGORY_COLOR;
		return CATEGORY_COLORS[String(cat).trim()] || DEFAULT_CATEGORY_COLOR;
	}

	function fmtTime(t) {
		return t ? t.replace("T", " ").replace("Z", " UTC") : "—";
	}

	// Towns are static reference data: loaded once at startup, drawn once, and
	// never rebuilt per bulletin.
	async function loadTowns() {
		try {
			const res = await fetch("data/towns.json");
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const data = await res.json();
			towns = data.towns || [];
			els.townsNote.className = "layer-note";
			els.townsNote.textContent = `${towns.length} locations`;
		} catch (err) {
			towns = [];
			els.townsNote.className = "layer-note error";
			els.townsNote.textContent =
				"data/towns.json missing — run build_towns_dataset.py";
		}
		drawTowns();
	}

	function drawTowns() {
		townsLayer.clearLayers();
		if (!els.towns.checked) return;
		towns.forEach((town) => {
			L.circleMarker([town.lat, town.lon], {
				pane: "towns",
				radius: town.major ? 4 : 3,
				color: "#111826",
				weight: 1,
				fillColor: town.major ? "#ffffff" : "#cfd8e6",
				fillOpacity: 0.9,
			})
				.bindTooltip(town.name, { direction: "top", offset: [0, -4] })
				.bindPopup(
					`
          <b>${town.name}</b>${town.state ? ` (${town.state})` : ""}<br>
          ${town.lat.toFixed(4)}, ${town.lon.toFixed(4)}<br>
          ${town.group ? `Group: ${town.group}<br>` : ""}
          ${town.coastalOrder !== null && town.coastalOrder !== undefined ? `Coastal order: ${town.coastalOrder}<br>` : ""}
          ${town.major ? "Major town<br>" : ""}
          ${town.island ? "Island town" : ""}
        `,
				)
				.addTo(townsLayer);
		});
	}

	async function loadIndex() {
		setStatus("Loading index…");
		const res = await fetch("data/index.json");
		if (!res.ok)
			throw new Error(`Failed to load data/index.json (${res.status})`);
		index = await res.json();
		setStatus("");
		populateCyclones();
	}

	function populateCyclones() {
		cyclonesById = new Map();
		Object.entries(index.regions || {}).forEach(([region, cyclones]) => {
			cyclones.forEach((cyclone) => {
				const existing = cyclonesById.get(cyclone.distId) || {
					...cyclone,
					regions: [],
					bulletinCount: 0,
					hasBestTrack: false,
				};
				existing.regions.push(region);
				existing.bulletinCount += cyclone.bulletinCount || 0;
				existing.hasBestTrack ||= Boolean(cyclone.hasBestTrack);
				if (!existing.distName && cyclone.distName)
					existing.distName = cyclone.distName;
				if (
					!existing.firstIssue ||
					(cyclone.firstIssue &&
						cyclone.firstIssue < existing.firstIssue)
				) {
					existing.firstIssue = cyclone.firstIssue;
				}
				if (
					!existing.lastIssue ||
					(cyclone.lastIssue &&
						cyclone.lastIssue > existing.lastIssue)
				) {
					existing.lastIssue = cyclone.lastIssue;
				}
				cyclonesById.set(cyclone.distId, existing);
			});
		});

		const cyclones = Array.from(cyclonesById.values()).sort((a, b) =>
			(a.firstIssue || "").localeCompare(b.firstIssue || ""),
		);
		const selectedId = els.cyclone.value;
		els.cyclone.replaceChildren(
			...cyclones.map((c) => {
				const name = c.distName
					? String(c.distName)
							.replace(/^Cyclone\s+/i, "")
							.trim()
					: c.distId;
				const label = `${name} - ${c.distId} (${c.bulletinCount} bulletins, ${c.firstIssue ? c.firstIssue.slice(0, 10) : "?"})${c.hasBestTrack ? " ★" : ""}`;
				return new Option(label, c.distId);
			}),
		);
		if (cyclones.length) {
			els.cyclone.value = cyclones.some((c) => c.distId === selectedId)
				? selectedId
				: cyclones[0].distId;
			loadCyclone();
			renderCompareSelectors();
		} else {
			els.cyclone.replaceChildren(
				new Option("No cyclones available", ""),
			);
			currentBulletins = [];
			renderBulletin();
		}
	}

	function cycloneOptions(selectedId) {
		return [
			new Option("Select a cyclone", ""),
			...Array.from(cyclonesById.values())
				.sort((a, b) =>
					(a.firstIssue || "").localeCompare(b.firstIssue || ""),
				)
				.map(
					(c) =>
						new Option(
							`${c.distName || c.distId} — ${c.distId}${c.hasBestTrack ? " ★" : ""}`,
							c.distId,
							false,
							c.distId === selectedId,
						),
				),
		];
	}

	function renderCompareSelectors() {
		if (!els.compareSelectors) return;
		els.compareSelectors.replaceChildren(
			...compareSelections.map((selectedId, index) => {
				const wrapper = document.createElement("div");
				wrapper.className = "compare-selector";
				const label = document.createElement("label");
				label.textContent = `Cyclone ${index + 1}`;
				const select = document.createElement("select");
				select.append(...cycloneOptions(selectedId));
				select.addEventListener("change", () => {
					compareSelections[index] = select.value;
					drawComparison();
				});
				wrapper.append(label, select);
				return wrapper;
			}),
		);
		els.addCompareCyclone.disabled = compareSelections.length >= 5;
	}

	function openComparison() {
		comparisonMode = true;
		if (!compareSelections.length)
			compareSelections = [els.cyclone.value || "", ""];
		els.comparePanel.hidden = false;
		els.compareToggle.textContent = "Back to visualizer options";
		els.compareToggle.setAttribute("aria-expanded", "true");
		document.getElementById("standardControls").hidden = true;
		bulletinLayer.clearLayers();
		ghostLayer.clearLayers();
		bestTrackLayer.clearLayers();
		townsLayer.clearLayers();
		compareAreaLayer.clearLayers();
		renderCompareSelectors();
		drawComparison();
	}

	function closeComparison() {
		comparisonMode = false;
		els.comparePanel.hidden = true;
		els.compareToggle.textContent = "Compare best tracks";
		els.compareToggle.setAttribute("aria-expanded", "false");
		document.getElementById("standardControls").hidden = false;
		comparisonLayer.clearLayers();
		drawTowns();
		compareAreaLayer.clearLayers();
		compareTracks = [];
		renderBulletin(true);
	}

	async function drawComparison() {
		if (!comparisonMode) return;
		comparisonLayer.clearLayers();
		compareAreaLayer.clearLayers();
		compareTracks = [];
		const selected = [...new Set(compareSelections.filter(Boolean))];
		if (!selected.length) {
			els.compareStatus.textContent = "Choose at least one cyclone.";
			els.compareTimeLabel.textContent = "—";
			return;
		}
		els.compareStatus.textContent = "Loading best tracks…";
		const tracks = await Promise.all(selected.map(loadBestTrack));
		if (!comparisonMode) return;
		const bounds = [];
		tracks.forEach((track, index) => {
			if (!track || track.points.length < 2) return;
			const color = COMPARE_COLORS[index];
			const latlngs = track.points.map((point) => [
				point.coord[1],
				point.coord[0],
			]);
			L.polyline(latlngs, { color, weight: 4, opacity: 0.9 })
				.bindPopup(
					`<b>${track.name || track.distId}</b><br>${bestTrackSummaryFor(track)}`,
				)
				.addTo(comparisonLayer);
			bounds.push(...latlngs);
			compareTracks.push({ track, color });
		});
		if (bounds.length)
			map.fitBounds(L.latLngBounds(bounds), {
				padding: [30, 30],
				maxZoom: 9,
			});

		updateCompareSlider(true, tracks.filter(Boolean).length);
	}

	function checkedCompareLevels() {
		return Object.keys(els.compareLevels).filter(
			(level) => els.compareLevels[level].checked,
		);
	}

	function hasRadius(p, levels) {
		return levels.some((level) => {
			const r = p.radii && p.radii[level];
			return (
				Boolean(r) &&
				[r.ne, r.se, r.sw, r.nw, r.mean].some(
					(v) => v !== null && v !== undefined && v > 0,
				)
			);
		});
	}

	// Wind radii are only analysed in short windows around some fixes (none at
	// genesis or decay, and gaps in between), so a time axis would mostly land
	// on empty steps. The slider instead steps through each cyclone's points
	// that have a radius for a ticked threshold, and shows every cyclone at its
	// n-th such point. Empty for the raw-fix fallback, which carries no radii.
	function updateCompareSlider(reset, available) {
		const levels = checkedCompareLevels();
		compareTracks.forEach((entry) => {
			entry.areaPoints =
				entry.track.source === "interpolated"
					? entry.track.points.filter((p) => hasRadius(p, levels))
					: [];
		});
		const longest = Math.max(
			0,
			...compareTracks.map((e) => e.areaPoints.length),
		);
		els.compareSlider.max = Math.max(0, longest - 1);
		els.compareSlider.step = 1;
		els.compareSlider.value = reset
			? 0
			: Math.min(
					Number(els.compareSlider.value) || 0,
					els.compareSlider.max,
				);
		drawCompareAreas(available);
	}

	// Wind areas (gale / storm / hurricane force, per the ticked boxes) of every
	// compared best track at the slider position, in each cyclone's own colour.
	function drawCompareAreas(available) {
		compareAreaLayer.clearLayers();
		const levels = checkedCompareLevels();
		els.compareTimeBar.hidden = !levels.length;
		if (available === undefined) available = compareTracks.length;

		let status = available
			? `${available} best track${available === 1 ? "" : "s"} shown.`
			: "No best-track data is available for the selected cyclones.";
		if (!levels.length || !compareTracks.length) {
			els.compareStatus.textContent = status;
			return;
		}

		const i = Number(els.compareSlider.value) || 0;
		const noRadii = [];
		const labelLines = [];
		compareTracks.forEach(({ track, color, areaPoints: pts }) => {
			const name = track.name || track.distId;
			if (!pts.length) {
				noRadii.push(name);
				return;
			}
			const p = pts[i];
			if (!p) {
				labelLines.push(`${name}: wind-radii analysis ended`);
				return;
			}
			labelLines.push(`${name}: ${fmtTime(p.time)}`);
			// Weakest threshold first so the smaller, stronger areas sit on top.
			levels.forEach((level) => {
				const polygon = buildAreaPolygon(
					p,
					level,
					BEST_TRACK_AREA_STYLE[level],
					color,
					name,
				);
				if (polygon) polygon.addTo(compareAreaLayer);
			});
			L.circleMarker([p.coord[1], p.coord[0]], {
				radius: 5,
				color: "#111826",
				weight: 1,
				fillColor: color,
				fillOpacity: 1,
			})
				.bindPopup(
					`<b>${name}</b><br>Time: ${fmtTime(p.time)}<br>${bestTrackPointDetails(p)}Max wind: ${p.windSpeed ?? "—"} kn`,
				)
				.addTo(compareAreaLayer);
		});
		const total = Number(els.compareSlider.max) + 1;
		els.compareTimeLabel.textContent =
			total > 1 || labelLines.length
				? [`Wind-radii point ${i + 1} of ${total}`, ...labelLines].join(
						"\n",
					)
				: "—";
		if (noRadii.length)
			status += ` No wind radii for ${noRadii.join(", ")} at the ticked thresholds (needs the API and an interpolation run).`;
		els.compareStatus.textContent = status;
	}

	// --- Best track -------------------------------------------------------
	//
	// The verification is scored on the interpolated 15-minute grid
	// (interpolated_point, written by app.services.interpolation), so the map
	// draws that same grid wherever it can get it: anything else would show a
	// track the contingency numbers were never computed against.
	//
	// The API only answers when the page is served by app.main (uvicorn) AND
	// `python -m app.cli interpolate` has produced a run. Served from a plain
	// `python -m http.server`, or before the DB is loaded, the fetch just fails
	// and we fall back to data/best_track/<id>.json -- the raw 6-hourly BOM
	// fixes from build_gml_dataset.py. Both are normalised to the same shape so
	// drawBestTrack() only has to care about `source`.
	const API_BASE = "api/v1";

	function normaliseTime(tm) {
		// FastAPI serialises the aware UTC datetimes as "...+00:00" or "...Z"
		// depending on the pydantic version; fmtTime() only understands the "Z".
		return (tm || "").replace("+00:00", "Z").replace(/\.\d+(?=Z?$)/, "");
	}

	// Wind radii (km) per threshold, keyed by quadrant. `mean` is the all-round
	// radius used when a quadrant is missing.
	function radiiFromRow(r) {
		const radii = {};
		for (const level of Object.keys(BEST_TRACK_AREA_STYLE)) {
			const k = level.toLowerCase();
			radii[level] = {
				ne: r[`mn_radius_${k}_secne`],
				se: r[`mn_radius_${k}_secse`],
				sw: r[`mn_radius_${k}_secsw`],
				nw: r[`mn_radius_${k}_secnw`],
				mean: r[`mn_radius_${k}_wind`],
			};
		}
		return radii;
	}

	// Quadrant radius for a compass bearing, or null when unknown. A quadrant
	// of 0 is data ("no wind of this force here", per the BoM spec) and is kept
	// as 0; only a missing (null) quadrant falls back to the mean radius, and if
	// that is missing or 0 too the radius is unknown. Note this is stricter than
	// get_quadrant_radius() in backend/app/gen_cont_tables.py, which also treats
	// a quadrant of 0 as "use the mean".
	function quadrantRadiusKm(radii, bearing) {
		const quadrant =
			bearing < 90
				? "ne"
				: bearing < 180
					? "se"
					: bearing < 270
						? "sw"
						: "nw";
		const q = radii[quadrant];
		if (q !== null && q !== undefined) return q;
		const m = radii.mean;
		if (m !== null && m !== undefined && m > 0) return m;
		return null;
	}

	// Point `km` away from (lat, lon) along `bearing` degrees (spherical earth;
	// the error is far below what is visible at map scale).
	function destinationPoint(lat, lon, bearing, km) {
		const R = 6371,
			d = km / R,
			b = (bearing * Math.PI) / 180;
		const phi1 = (lat * Math.PI) / 180,
			lam1 = (lon * Math.PI) / 180;
		const phi2 = Math.asin(
			Math.sin(phi1) * Math.cos(d) +
				Math.cos(phi1) * Math.sin(d) * Math.cos(b),
		);
		const lam2 =
			lam1 +
			Math.atan2(
				Math.sin(b) * Math.sin(d) * Math.cos(phi1),
				Math.cos(d) - Math.sin(phi1) * Math.sin(phi2),
			);
		return [
			(phi2 * 180) / Math.PI,
			(((lam2 * 180) / Math.PI + 540) % 360) - 180,
		];
	}

	// Ring of [lat, lon] for one threshold, or null if no bearing has a radius
	// above 0. Bearings with a zero or unknown radius collapse onto the centre,
	// so they leave a notch instead of an invented area.
	function windAreaRing(lat, lon, radii) {
		const ring = [];
		let any = false;
		for (let bearing = 0; bearing < 360; bearing += 3) {
			const km = quadrantRadiusKm(radii, bearing);
			if (km === null || km <= 0) {
				ring.push([lat, lon]);
				continue;
			}
			any = true;
			ring.push(destinationPoint(lat, lon, bearing, km));
		}
		return any ? ring : null;
	}

	function parseUtc(t) {
		if (!t) return NaN;
		return Date.parse(t.includes("T") ? t : t.replace(" ", "T") + "Z");
	}

	// The best-track point closest in time to `timeIso`, but only if it is
	// within one grid step -- otherwise the bulletin is outside the track.
	function nearestBestTrackPoint(points, timeIso) {
		const target = parseUtc(timeIso);
		if (!Number.isFinite(target) || !points.length) return null;
		const stepMs = (trackStepMinutes(points) || 360) * 60000;
		let best = null,
			bestDiff = Infinity;
		for (const p of points) {
			const diff = Math.abs(parseUtc(p.time) - target);
			if (diff < bestDiff) {
				best = p;
				bestDiff = diff;
			}
		}
		return bestDiff <= stepMs ? best : null;
	}

	// The API serves max_wind_spd in m/s; the popups and thresholds are in knots.
	function msToKnots(ms) {
		return ms === null || ms === undefined
			? null
			: Math.round(ms * 1.943844);
	}

	// Australian tropical cyclone category from max wind in knots (BoM scale).
	// Best-track data stores no category, so it is derived; null below Cat 1.
	function categoryFromKnots(kn) {
		if (kn === null || kn === undefined) return null;
		if (kn >= 108) return 5;
		if (kn >= 86) return 4;
		if (kn >= 64) return 3;
		if (kn >= 48) return 2;
		if (kn >= 34) return 1;
		return null;
	}

	function bestTrackPointDetails(p) {
		const [lon, lat] = p.coord;
		const cat = categoryFromKnots(p.windSpeed);
		return `Lat/Lon: ${lat.toFixed(2)}, ${lon.toFixed(2)}<br>
        Category: ${cat ?? "—"}<br>`;
	}

	async function loadInterpolatedTrack(distId) {
		// 404 here is routine: unknown disturbance, or no interpolation run yet.
		const res = await fetch(
			`${API_BASE}/disturbances/${encodeURIComponent(distId)}/interpolated-track`,
		);
		if (!res.ok) return null;
		const rows = await res.json();
		const points = rows
			.filter((r) => r.lat !== null && r.lon !== null)
			.map((r) => ({
				time: normaliseTime(r.tm),
				coord: [r.lon, r.lat],
				pressure: null, // not carried on the interpolated grid
				windSpeed: msToKnots(r.max_wind_spd),
				interpolated: Boolean(r.is_interpolated),
				radii: radiiFromRow(r),
			}));
		if (points.length < 2) return null;
		const cyclone = cyclonesById.get(distId);
		return {
			distId,
			name: cyclone ? cyclone.distName : null,
			source: "interpolated",
			points,
		};
	}

	async function loadStaticBestTrack(distId) {
		const res = await fetch(
			`data/best_track/${encodeURIComponent(distId)}.json`,
		);
		if (!res.ok) return null;
		const data = await res.json();
		// BoM's MAX_WIND_SPD is m/s (as the API serves it); the popups are in knots.
		const points = (data.points || []).map((p) => ({
			...p,
			windSpeed: msToKnots(p.windSpeed),
			interpolated: false,
		}));
		if (!points.length) return null;
		return { ...data, source: "observed", points };
	}

	async function loadBestTrack(distId) {
		try {
			const interpolated = await loadInterpolatedTrack(distId);
			if (interpolated) return interpolated;
		} catch (err) {
			// No API on this origin -- fall through to the static file.
		}
		try {
			return await loadStaticBestTrack(distId);
		} catch (err) {
			return null;
		}
	}

	// Minutes between the first two points, for the popup. Read off the data
	// rather than from the run row: there is no endpoint serving step_minutes.
	function trackStepMinutes(points) {
		if (points.length < 2) return null;
		const step =
			(Date.parse(
				points[1].time + (points[1].time.endsWith("Z") ? "" : "Z"),
			) -
				Date.parse(
					points[0].time + (points[0].time.endsWith("Z") ? "" : "Z"),
				)) /
			60000;
		return Number.isFinite(step) && step > 0 ? Math.round(step) : null;
	}

	function bestTrackSummary() {
		return bestTrackSummaryFor(currentBestTrack);
	}

	function bestTrackSummaryFor(track) {
		if (!track) return "not available";
		const n = track.points.length;
		if (track.source !== "interpolated")
			return `${n} points (raw 6-hourly BoM fixes; wind areas unavailable without the API)`;
		const step = trackStepMinutes(track.points);
		return `${n} points (interpolated${step ? ` ${step}-minute` : ""} grid, as verified)`;
	}

	async function loadCyclone() {
		stopPlay();
		const distId = els.cyclone.value;
		if (!distId) {
			currentBulletins = [];
			renderBulletin();
			return;
		}
		const cyclone = cyclonesById.get(distId);
		const regions = cyclone ? cyclone.regions : [];
		setStatus(
			`Loading ${distId} across ${regions.length} data source${regions.length === 1 ? "" : "s"}…`,
		);
		try {
			const results = await Promise.all(
				regions.map(async (region) => {
					const path = `data/${encodeURIComponent(region)}/${encodeURIComponent(distId)}.json`;
					const res = await fetch(path);
					if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
					return res.json();
				}),
			);
			currentBulletins = results
				.flat()
				.sort(
					(a, b) =>
						(a.fcastTime || "").localeCompare(b.fcastTime || "") ||
						(a.source || "").localeCompare(b.source || "") ||
						(a.issueTime || "").localeCompare(b.issueTime || ""),
				);
			setStatus("");
		} catch (err) {
			currentBulletins = [];
			setStatus(
				`Could not load data (are you running a local server? see README) — ${err.message}`,
				true,
			);
		}
		// Best track is per-cyclone (not per-region), post-event reanalysis data.
		// Not every cyclone has one, so a missing track is expected, not an error.
		currentBestTrack = await loadBestTrack(distId);
		currentIdx = 0;
		els.slider.min = 0;
		els.slider.max = Math.max(0, currentBulletins.length - 1);
		els.slider.value = 0;
		renderBulletin(true);
	}

	function drawGhostTrails() {
		ghostLayer.clearLayers();
		if (!els.layers.allBulletins.checked) return;
		currentBulletins.forEach((b, i) => {
			(b.tracks || []).forEach((track) => {
				if (track.coords.length < 2) return;
				L.polyline(toLatLngs(track.coords), {
					color: i === currentIdx ? "transparent" : "#8892a6",
					weight: 1,
					opacity: 0.35,
					dashArray: track.trackType === "Observed" ? "3,4" : null,
				}).addTo(ghostLayer);
			});
		});
	}

	// Past this many points, the interpolated grid is drawn as the line plus its
	// 6-hourly anchors only. Every 15-minute step gets its own circleMarker
	// below that, which is what makes the grid inspectable rather than a
	// featureless polyline; thousands of them just make panning stutter.
	const MAX_INTERPOLATED_MARKERS = 1200;

	// Wind areas for the best-track point nearest the bulletin's forecast base
	// time, so they move with the bulletin slider. Drawn first so the track line
	// and markers sit on top.
	function drawBestTrackAreas(points, bulletin, bounds) {
		if (!bulletin) return;
		const p = nearestBestTrackPoint(
			points,
			bulletin.fcastTime || bulletin.issueTime,
		);
		if (!p || !p.radii) return;
		Object.entries(BEST_TRACK_AREA_STYLE).forEach(([level, style]) => {
			if (!els.layers[style.layerKey].checked) return;
			const polygon = buildAreaPolygon(p, level, style);
			if (!polygon) return;
			polygon.addTo(bestTrackLayer);
			bounds.push(...polygon.getLatLngs()[0]);
		});
	}

	// Dashed wind-area polygon for one threshold at best-track point `p`, or
	// null if no radius is known. `color` / `name` default to the level's style
	// and the plain "Best track" title; compare mode passes the cyclone's own.
	function buildAreaPolygon(
		p,
		level,
		style,
		color = style.color,
		name = null,
	) {
		const [lon, lat] = p.coord;
		const r = p.radii[level];
		const ring = windAreaRing(lat, lon, r);
		if (!ring) return null;
		const km = (v) =>
			v === null || v === undefined ? "—" : `${Math.round(v)} km`;
		return L.polygon(ring, {
			color,
			fillColor: color,
			fillOpacity: style.fillOpacity,
			weight: 2,
			dashArray: "6,4",
			smoothFactor: 0,
		})
			.bindPopup(`<b>${name ? `${name} — ` : "Best track — "}${style.label}</b><br>
      Time: ${fmtTime(p.time)}${p.interpolated ? " (interpolated)" : ""}<br>
      NE ${km(r.ne)}, SE ${km(r.se)}, SW ${km(r.sw)}, NW ${km(r.nw)}<br>
      Mean ${km(r.mean)}`);
	}

	// Union of the best-track gale areas over [startH, endH] after the bulletin's
	// base time: where gale-force wind was actually observed in that window, to
	// set against the bulletin's Watch area. The ring is built exactly as for the
	// T+0 areas (windAreaRing), sampled every ~30 minutes to keep the union cheap.
	// Hours after the bulletin's base time that the observed gale area covers,
	// read from the From / To inputs. Out-of-range or inverted values are
	// clamped to 0..GALE_WINDOW_MAX_H with To > From, and written back so the
	// inputs always show what is drawn.
	function galeWindowHours() {
		let startH = Math.round(Number(els.galeFrom.value));
		let endH = Math.round(Number(els.galeTo.value));
		if (!Number.isFinite(startH)) startH = 0;
		if (!Number.isFinite(endH)) endH = 48;
		startH = Math.min(Math.max(startH, 0), GALE_WINDOW_MAX_H - 1);
		endH = Math.min(Math.max(endH, startH + 1), GALE_WINDOW_MAX_H);
		els.galeFrom.value = startH;
		els.galeTo.value = endH;
		return { startH, endH };
	}

	function drawObservedGaleWindow(points, bulletin) {
		galeWindowNote = "";
		if (!bulletin || !els.layers.btGaleWindow.checked) return;
		const base = parseUtc(bulletin.fcastTime || bulletin.issueTime);
		if (!Number.isFinite(base)) return;
		const { startH, endH } = galeWindowHours();
		const start = base + startH * 3600000;
		const end = base + endH * 3600000;
		const inWindow = points.filter((p) => {
			const t = parseUtc(p.time);
			return t >= start && t <= end;
		});
		// Every point's ring (null where no gale radius is known). The union uses
		// roughly half-hourly ones: unioning all 15-minute rings took ~400 ms per
		// redraw, too slow for the slider and play button, while 30 minutes costs
		// ~75 ms and the track moves only a few km between samples. Sampling is by
		// index, not clock-aligned, because the base time can be an off-hour issue
		// time; the first and last point in the window are always included so the
		// window's ends are not trimmed.
		const allRings = inWindow.map((p) =>
			p.radii ? windAreaRing(p.coord[1], p.coord[0], p.radii.GF) : null,
		);
		const stride = Math.max(
			1,
			Math.round(30 / (trackStepMinutes(points) || 30)),
		);
		const rings = allRings.filter(
			(ring, i) =>
				ring && (i % stride === 0 || i === allRings.length - 1),
		);
		galeWindowNote = `Observed gale ${startH}–${endH} h: ${allRings.filter(Boolean).length} of ${inWindow.length} best-track points in the window have gale radii`;
		if (!rings.length) return;

		const label = `${fmtTime(new Date(start).toISOString())} → ${fmtTime(new Date(end).toISOString())}`;
		const popup = `<b>Observed gale area (34 kn) — from best-track area</b><br>T+${startH} h → T+${endH} h: ${label}<br>${galeWindowNote.replace(/^Observed gale [^:]*: /, "")}`;
		const style = {
			color: GALE_WINDOW.color,
			fillColor: GALE_WINDOW.color,
			fillOpacity: GALE_WINDOW.fillOpacity,
			weight: 2,
			dashArray: "2,5",
			smoothFactor: 0,
		};
		try {
			// polygon-clipping works in [lon, lat]; a failure (library blocked, or a
			// degenerate ring) falls through to drawing the hourly rings overlapped.
			const union = polygonClipping.union(
				...rings.map((r) => [[r.map(([lat, lon]) => [lon, lat])]]),
			);
			union.forEach((polygon) => {
				L.polygon(
					polygon.map((ring) => ring.map(([lon, lat]) => [lat, lon])),
					style,
				)
					.bindPopup(popup)
					.addTo(bestTrackLayer);
			});
		} catch (err) {
			rings.forEach((ring) => {
				L.polygon(ring, { ...style, weight: 1, fillOpacity: 0.05 })
					.bindPopup(popup)
					.addTo(bestTrackLayer);
			});
		}
	}

	function drawBestTrack(bounds, bulletin) {
		bestTrackLayer.clearLayers();
		if (!currentBestTrack) return;
		const points = currentBestTrack.points || [];
		if (points.length < 2) return;

		const interpolated = currentBestTrack.source === "interpolated";
		const step = interpolated ? trackStepMinutes(points) : null;
		const anchors = points.filter((p) => !p.interpolated);
		const showEveryPoint =
			!interpolated || points.length <= MAX_INTERPOLATED_MARKERS;

		// The wind areas have their own checkboxes, so they draw whether or not
		// the track line itself is shown.
		if (interpolated) {
			drawObservedGaleWindow(points, bulletin);
			drawBestTrackAreas(points, bulletin, bounds);
		}
		if (!els.layers.bestTrack.checked) return;

		const latlngs = points.map((p) => [p.coord[1], p.coord[0]]);
		L.polyline(latlngs, { color: "#2fd4d9", weight: 3, opacity: 0.9 })
			.bindPopup(
				`<b>Best track</b>${currentBestTrack.name ? ` — ${currentBestTrack.name}` : ""}<br>
        ${
			interpolated
				? `Interpolated grid${step ? ` (${step}-minute step)` : ""} — ${points.length} points from ${anchors.length} BOM fixes`
				: `Raw BOM fixes — ${points.length} points`
		}<br>
        ${fmtTime(points[0].time)} → ${fmtTime(points[points.length - 1].time)}`,
			)
			.addTo(bestTrackLayer);

		(showEveryPoint ? points : anchors).forEach((p) => {
			const [lon, lat] = p.coord;
			const isAnchor = !p.interpolated;
			L.circleMarker([lat, lon], {
				radius: isAnchor ? 7 : 3.5,
				color: "#111826",
				weight: 1,
				fillColor: "#2fd4d9",
				fillOpacity: isAnchor ? 0.95 : 0.7,
			})
				.bindPopup(
					`<b>${isAnchor ? "Best track fix" : "Interpolated point"}</b><br>
        Time: ${fmtTime(p.time)}<br>
        ${bestTrackPointDetails(p)}
        ${p.pressure === null || p.pressure === undefined ? "" : `Pressure: ${p.pressure} hPa<br>`}
        Max wind: ${p.windSpeed ?? "—"} kn`,
				)
				.addTo(bestTrackLayer);
		});

		bounds.push(...latlngs);
	}

	function renderBulletin(fitBounds) {
		bulletinLayer.clearLayers();
		drawGhostTrails();
		const b = currentBulletins[currentIdx];
		if (!b) {
			els.label.textContent = "No bulletins available.";
			els.info.textContent = "Select a cyclone to begin.";
			els.prev.disabled = els.next.disabled = true;
			drawBestTrack([]);
			return;
		}
		els.prev.disabled = currentIdx === 0;
		els.next.disabled = currentIdx === currentBulletins.length - 1;
		els.slider.value = currentIdx;
		els.label.innerHTML = `Bulletin <b>${currentIdx + 1}/${currentBulletins.length}</b> — ${fmtTime(b.fcastTime)}`;
		els.info.innerHTML = `<b>${b.distName || ""}</b> (${b.distId})<br>
      Source: ${b.source}<br>Time: ${fmtTime(b.fcastTime)}<br>
      Issued: ${fmtTime(b.issueTime)}<br>Expiry: ${b.expiryHrs || "?"} hrs<br>
      Tracks: ${b.tracks.length}, Fixes: ${b.fixes.length}, Areas: ${b.areas.length}<br>
      Best track: ${bestTrackSummary()}`;

		const bounds = [];
		if (els.layers.tracks.checked) {
			b.tracks.forEach((track) => {
				if (track.coords.length < 2) return;
				const latlngs = toLatLngs(track.coords);
				L.polyline(latlngs, {
					color:
						track.trackType === "Forecast" ? "#4fa8ff" : "#ffd24f",
					weight: 3,
					opacity: 0.9,
					dashArray: track.trackType === "Observed" ? "6,5" : null,
				})
					.bindPopup(
						`<b>${track.trackType || "Track"}</b><br>${fmtTime(track.startTime)} → ${fmtTime(track.endTime)}`,
					)
					.addTo(bulletinLayer);
				bounds.push(...latlngs);
			});
		}
		if (els.layers.fixes.checked) {
			b.fixes.forEach((fix) => {
				const [lon, lat] = fix.coord;
				const marker = L.circleMarker([lat, lon], {
					radius: fix.fixType === "Current" ? 8 : 6,
					color: "#111826",
					weight: 1.5,
					fillColor: categoryColor(fix.category),
					fillOpacity: 0.95,
				})
					.bindPopup(`<b>${fix.fixType || "Fix"}</b> (${fix.symbol || "?"})<br>
          Category: ${fix.category ?? "—"}<br>Time: ${fmtTime(fix.fixTime)}<br>
          Offset: ${fix.timeOffset ?? "0"}h`);
				marker.addTo(bulletinLayer);
				bounds.push([lat, lon]);
			});
		}
		(b.areas || []).forEach((area) => {
			const baseStyle = AREA_STYLE[area.kind];
			const windAreaColor =
				area.kind === "tcWindArea"
					? WIND_AREA_COLORS[area.fixType]
					: null;
			const style = windAreaColor
				? {
						...baseStyle,
						color: windAreaColor,
						fillColor: windAreaColor,
					}
				: baseStyle;
			if (!style || !els.layers[style.layerKey].checked) return;
			const popup = `<b>${area.kind}</b><br>
        ${area.areaType ? `Area type: ${area.areaType}<br>` : ""}
        ${area.extent ? `Extent: ${area.extent}<br>` : ""}
        ${area.windType ? `Wind type: ${area.windType}<br>` : ""}
        ${area.marineType ? `Marine type: ${area.marineType}<br>` : ""}
        ${area.fixType ? `Fix type: ${area.fixType}<br>` : ""}
        ${area.fixTime ? `Fix time: ${fmtTime(area.fixTime)}` : ""}`;
			area.polygons.forEach((rings) => {
				const latlngRings = rings.map(toLatLngs);
				L.polygon(latlngRings, {
					color: style.color,
					fillColor: style.fillColor,
					fillOpacity: style.fillOpacity,
					weight: style.weight,
					smoothFactor: 0,
				})
					.bindPopup(popup)
					.addTo(bulletinLayer);
				latlngRings.forEach((ring) => bounds.push(...ring));
			});
		});
		drawBestTrack(bounds, b);
		if (galeWindowNote) els.info.innerHTML += `<br>${galeWindowNote}`;
		if (fitBounds && bounds.length)
			map.fitBounds(L.latLngBounds(bounds), {
				padding: [30, 30],
				maxZoom: 9,
			});
	}

	function stopPlay() {
		if (playTimer) {
			clearInterval(playTimer);
			playTimer = null;
			els.play.textContent = "⏵";
		}
	}

	function togglePlay() {
		if (playTimer) {
			stopPlay();
			return;
		}
		if (!currentBulletins.length) return;
		els.play.textContent = "⏸";
		playTimer = setInterval(() => {
			if (currentIdx >= currentBulletins.length - 1) {
				stopPlay();
				return;
			}
			currentIdx += 1;
			renderBulletin(false);
		}, 700);
	}

	els.cyclone.addEventListener("change", loadCyclone);
	els.uploadGmlBtn.addEventListener("click", () =>
		els.gmlUploadInput.click(),
	);
	els.gmlUploadInput.addEventListener("change", async (event) => {
		const file = event.target.files[0];
		if (!file) return;
		try {
			await uploadDataset(file, "upload", "GML archive");
		} finally {
			event.target.value = "";
		}
	});

	els.refreshBestTrackBtn.addEventListener("click", async () => {
		els.refreshBestTrackBtn.disabled = true;
		els.uploadGmlBtn.disabled = true;
		try {
			await uploadDataset(null, "refresh-best-track", "best track");
		} finally {
			els.refreshBestTrackBtn.disabled = false;
			els.uploadGmlBtn.disabled = false;
		}
	});

	els.slider.addEventListener("input", () => {
		stopPlay();
		currentIdx = Number(els.slider.value);
		renderBulletin(false);
	});
	els.prev.addEventListener("click", () => {
		stopPlay();
		if (currentIdx > 0) {
			currentIdx--;
			renderBulletin(false);
		}
	});
	els.next.addEventListener("click", () => {
		stopPlay();
		if (currentIdx < currentBulletins.length - 1) {
			currentIdx++;
			renderBulletin(false);
		}
	});
	els.play.addEventListener("click", togglePlay);
	Object.values(els.layers).forEach((cb) =>
		cb.addEventListener("change", () => renderBulletin(false)),
	);
	[els.galeFrom, els.galeTo].forEach((inp) =>
		inp.addEventListener("change", () => renderBulletin(false)),
	);
	els.towns.addEventListener("change", drawTowns);

	initBasemap();
	loadTowns();
	loadIndex().catch((err) => setStatus(err.message, true));
})();
