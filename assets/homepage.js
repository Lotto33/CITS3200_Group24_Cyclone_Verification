const status = document.getElementById("initializationStatus");
let initializationRequested = false;

document.querySelectorAll("[data-destination]").forEach(link => {
	link.addEventListener("click", () => {
		if (initializationRequested) return;
		initializationRequested = true;
		status.textContent = "Checking backend data readiness...";
		fetch("initialize")
			.then(response => response.json())
			.then(data => { status.textContent = data.message; })
			.catch(() => {
				status.textContent = "The page opened, but backend readiness could not be checked.";
			});
	});
});
