(function (global) {
	"use strict";

	global.formatCycloneTime = function formatCycloneTime(value) {
		if (value === null || value === undefined || value === "") return "";
		const text = String(value);
		const match = text.match(
			/^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$/i,
		);
		if (!match) return text;

		const [, date, hour, minute, timezone] = match;
		const zone = timezone
			? /^z$/i.test(timezone) || /^[+-]00:?00$/.test(timezone)
				? " UTC"
				: ` ${timezone}`
			: "";
		return `${date} ${hour}:${minute}${zone}`;
	};
})(window);
