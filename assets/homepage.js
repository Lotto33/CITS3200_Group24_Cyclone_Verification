const status = document.getElementById("initializationStatus");
let initializationRequested = false;

document.querySelectorAll("[data-destination]").forEach(link => {
	link.addEventListener("click", () => {
		if (initializationRequested) return;
		initializationRequested = true;
		status.textContent = "Starting the backend data initialization…";
		fetch("initialize", { method: "POST" })
			.then(response => response.json())
			.then(data => { status.textContent = data.message; })
			.catch(() => {
				status.textContent = "The page opened, but backend initialization could not be started.";
			});
	});
});
