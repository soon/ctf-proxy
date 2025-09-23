import dayjs from "dayjs";

interface SparklineChartProps {
	time_series: Array<{ timestamp: number; count: number }>;
	windowMinutes: number;
	globalHoverTimestamp: number | null;
	onHoverChange: (timestamp: number | null) => void;
	isCustomRange?: boolean;
	search?: any;
}

export function SparklineChart({
	time_series,
	windowMinutes,
	globalHoverTimestamp,
	onHoverChange,
	isCustomRange = false,
	search = {},
}: SparklineChartProps) {
	const width = 280;
	const height = 40;
	const padding = 4;

	// Determine time range based on context
	let minTime: number;
	let maxTime: number;
	let totalMinutes: number;

	if (isCustomRange && search.startTime && search.endTime) {
		// Custom range: use exact start/end times
		minTime = dayjs(search.startTime).valueOf();
		maxTime = dayjs(search.endTime).valueOf();
		totalMinutes = Math.ceil((maxTime - minTime) / 60000);
	} else {
		// Rolling window: calculate from current time
		const now = Date.now();
		maxTime = Math.floor(now / 60000) * 60000; // Round down to minute
		minTime = maxTime - windowMinutes * 60000;
		totalMinutes = windowMinutes;
	}

	// Create a Map for quick lookup of actual data
	const dataMap = new Map<number, number>();
	if (time_series && time_series.length > 0) {
		time_series.forEach((point) => {
			// Round timestamp to nearest minute
			const minuteTimestamp = Math.floor(point.timestamp / 60000) * 60000;
			dataMap.set(minuteTimestamp, point.count);
		});
	}

	// Build complete dataset with 0s for missing minutes
	const completeData: number[] = [];
	for (let i = 0; i < totalMinutes; i++) {
		const timestamp = minTime + i * 60000;
		completeData.push(dataMap.get(timestamp) || 0);
	}

	// Skip rendering if no data at all
	const hasAnyData = completeData.length > 0 && completeData.some((v) => v > 0);
	if (!hasAnyData) {
		return (
			<div
				style={{
					width: "280px",
					height: 50,
					display: "flex",
					alignItems: "center",
					justifyContent: "center",
					color: "#999",
				}}
			>
				No data
			</div>
		);
	}

	// Get value range
	const maxValue = Math.max(...completeData, 1);

	// Calculate hover info based on global timestamp
	let hoverInfo: { time: string; value: number } | null = null;
	if (globalHoverTimestamp !== null) {
		// Find the closest minute timestamp
		const minuteTimestamp = Math.floor(globalHoverTimestamp / 60000) * 60000;
		const index = Math.floor((minuteTimestamp - minTime) / 60000);
		if (index >= 0 && index < completeData.length) {
			hoverInfo = {
				time: dayjs(minuteTimestamp).format("MMM D, HH:mm"),
				value: completeData[index],
			};
		}
	}

	// Generate SVG path for continuous line
	const xStep = (width - 2 * padding) / (completeData.length - 1 || 1);
	const yScale = (height - 2 * padding) / (maxValue || 1);

	const points = completeData.map((value, index) => {
		const x = padding + index * xStep;
		const y = height - padding - value * yScale;
		return `${x},${y}`;
	});

	const pathData = `M ${points.join(" L ")}`;

	// Create area under the line
	const areaPoints = [
		`${padding},${height - padding}`,
		...points,
		`${width - padding},${height - padding}`,
	];
	const areaData = `M ${areaPoints.join(" L ")} Z`;

	return (
		<div style={{ width: "280px", height: 50, padding: "5px 0" }}>
			<svg
				width={width}
				height={height}
				style={{ display: "block" }}
				onMouseLeave={() => onHoverChange(null)}
			>
				{/* Grid line at zero */}
				<line
					x1={padding}
					y1={height - padding}
					x2={width - padding}
					y2={height - padding}
					stroke="#f0f0f0"
					strokeWidth="1"
				/>

				{/* Area under line */}
				<path d={areaData} fill="#1890ff" opacity="0.1" />

				{/* Main line */}
				<path d={pathData} fill="none" stroke="#1890ff" strokeWidth="1.5" />

				{/* Interactive overlay for hover - sample points for performance */}
				{(() => {
					// For large datasets, sample points for hover (max 100 points)
					const step = Math.max(1, Math.floor(completeData.length / 100));
					const hoverPoints = [];

					for (let i = 0; i < completeData.length; i += step) {
						const value = completeData[i];
						const x = padding + i * xStep;
						const y = height - padding - value * yScale;
						const timestamp = minTime + i * 60000;

						hoverPoints.push(
							<g key={i}>
								{/* Invisible hover area */}
								<rect
									x={x - (xStep * step) / 2}
									y={0}
									width={xStep * step}
									height={height}
									fill="transparent"
									style={{ cursor: "crosshair" }}
									onMouseEnter={() => {
										onHoverChange(timestamp);
									}}
								/>
								{/* Visible dot on hover */}
								<circle
									cx={x}
									cy={y}
									r="3"
									fill="#1890ff"
									opacity={
										globalHoverTimestamp !== null &&
										Math.abs(timestamp - globalHoverTimestamp) < 60000
											? "1"
											: "0"
									}
									pointerEvents="none"
								/>
							</g>,
						);
					}

					return hoverPoints;
				})()}
				{/* Show hover info or max value in top left corner */}
				<text
					x={padding + 2}
					y={padding + 10}
					fontSize="11"
					fill="#666"
					fontWeight="500"
				>
					{hoverInfo
						? `${hoverInfo.time}: ${hoverInfo.value}`
						: `max: ${maxValue}`}
				</text>
			</svg>
		</div>
	);
}
