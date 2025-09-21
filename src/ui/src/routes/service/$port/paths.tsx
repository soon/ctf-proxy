import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { getServicePathStatsApiServicesPortPathsGetOptions } from "@/client/@tanstack/react-query.gen";
import {
	Table,
	Tag,
	Button,
	Empty,
	Spin,
	Typography,
	Alert,
	Select,
	Space,
	DatePicker,
	Modal,
} from "antd";
import {
	ReloadOutlined,
	ClockCircleOutlined,
	CalendarOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import dayjs from "dayjs";
import { z } from "zod";

const { RangePicker } = DatePicker;

const { Text } = Typography;

function SparklineChart({
	time_series,
	isCustomRange,
	search,
	windowMinutes,
	globalHoverTimestamp,
	onHoverChange,
}: {
	time_series: Array<{ timestamp: number; count: number }>;
	isCustomRange: boolean;
	search: any;
	windowMinutes: number;
	globalHoverTimestamp: number | null;
	onHoverChange: (timestamp: number | null) => void;
}) {
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
	if (completeData.length === 0 || completeData.every((v) => v === 0)) {
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

const pathSearchSchema = z.object({
	window: z.number().optional().default(60),
	autoRefresh: z.boolean().optional().default(true),
	startTime: z.string().optional(),
	endTime: z.string().optional(),
});

export const Route = createFileRoute("/service/$port/paths")({
	component: PathStats,
	validateSearch: pathSearchSchema,
	staticData: {
		breadcrumb: "Path Stats",
	},
});

function PathStats() {
	const { port } = Route.useParams();
	const search = Route.useSearch();
	const navigate = useNavigate();
	const portNumber = parseInt(port);

	const windowMinutes = search.window;
	const autoRefresh = search.autoRefresh;
	// Treat as custom range if it has date parameters
	const isCustomRange = !!(search.startTime && search.endTime);

	const [globalHoverTimestamp, setGlobalHoverTimestamp] = useState<
		number | null
	>(null);
	const [customRangeModalVisible, setCustomRangeModalVisible] = useState(false);
	const [customRange, setCustomRange] = useState<
		[dayjs.Dayjs, dayjs.Dayjs] | null
	>(
		isCustomRange && search.startTime && search.endTime
			? [dayjs(search.startTime), dayjs(search.endTime)]
			: null,
	);

	const updateSearch = (updates: Partial<typeof search>) => {
		navigate({
			to: `/service/${port}/paths`,
			search: (prev) => ({ ...prev, ...updates }),
			replace: true,
		});
	};

	const getCustomRangeLabel = () => {
		if (isCustomRange && search.startTime && search.endTime) {
			const start = dayjs(search.startTime);
			const end = dayjs(search.endTime);
			return `${start.format("MMM D")} - ${end.format("MMM D, YYYY")}`;
		}
		return "Custom range...";
	};

	const windowOptions = [
		{ value: 5, label: "Last 5 minutes" },
		{ value: 15, label: "Last 15 minutes" },
		{ value: 30, label: "Last 30 minutes" },
		{ value: 60, label: "Last hour" },
		{ value: 120, label: "Last 2 hours" },
		{ value: 360, label: "Last 6 hours" },
		{ value: 720, label: "Last 12 hours" },
		{ value: 1440, label: "Last 24 hours" },
		{ value: 10080, label: "Last week" },
		{ value: -1, label: getCustomRangeLabel() },
	];

	// Add custom range option if it's currently selected
	const selectOptions = isCustomRange ? [...windowOptions] : windowOptions;

	// Determine the select value
	const selectValue = isCustomRange ? -1 : windowMinutes;

	const handleWindowChange = (value: number) => {
		if (value === -1) {
			setCustomRangeModalVisible(true);
		} else {
			updateSearch({
				window: value,
				startTime: undefined,
				endTime: undefined,
			});
			setCustomRange(null);
		}
	};

	const handleCustomRangeOk = () => {
		if (customRange) {
			const [start, end] = customRange;
			const minutes = Math.round(end.diff(start, "minute"));
			updateSearch({
				window: minutes,
				startTime: start.toISOString(),
				endTime: end.toISOString(),
			});
			setCustomRangeModalVisible(false);
		}
	};

	const queryParams: any = {
		path: { port: portNumber },
	};

	// Use start/end time for custom ranges, window_minutes for rolling windows
	if (isCustomRange && search.startTime && search.endTime) {
		queryParams.query = {
			start_time: search.startTime,
			end_time: search.endTime,
		};
	} else {
		queryParams.query = {
			window_minutes: windowMinutes,
		};
	}

	const { data, isLoading, error, refetch, isFetching } = useQuery({
		...getServicePathStatsApiServicesPortPathsGetOptions(queryParams),
		refetchInterval: autoRefresh ? 10000 : false, // Refresh every 10 seconds if auto-refresh is on
	});

	// Update to rolling window - refresh every minute
	useEffect(() => {
		if (autoRefresh) {
			const interval = setInterval(() => {
				refetch();
			}, 60000); // Refresh every minute for rolling window
			return () => clearInterval(interval);
		}
	}, [autoRefresh, refetch]);

	if (isLoading) {
		return (
			<div className="flex justify-center items-center h-64">
				<Spin size="large" tip="Loading path statistics..." />
			</div>
		);
	}

	if (error || !data) {
		return (
			<div className="flex justify-center items-center h-64">
				<Empty description={error?.message || "Path stats not available"} />
			</div>
		);
	}

	const { paths, service_name, service_port, ignored_paths, window_minutes } =
		data;

	// Extract values for use in the component
	const totalMinutes = window_minutes || windowMinutes;

	const columns: ColumnsType<any> = [
		{
			title: "Method",
			dataIndex: "method",
			key: "method",
			width: 80,
			render: (method: string) => (
				<Tag
					color={
						method === "GET"
							? "blue"
							: method === "POST"
								? "green"
								: method === "PUT"
									? "orange"
									: method === "DELETE"
										? "red"
										: "default"
					}
				>
					{method}
				</Tag>
			),
		},
		{
			title: "Path",
			dataIndex: "path",
			key: "path",
			ellipsis: true,
			render: (path: string) => (
				<Text code className="text-xs">
					{path}
				</Text>
			),
		},
		{
			title: "Total Count",
			dataIndex: "total_count",
			key: "total_count",
			width: 120,
			sorter: (a: any, b: any) => b.total_count - a.total_count,
			render: (count: number) => <Text strong>{count.toLocaleString()}</Text>,
		},
		{
			title: `Sparkline (${
				isCustomRange && search.startTime && search.endTime
					? `${dayjs(search.startTime).format("MMM D")} - ${dayjs(search.endTime).format("MMM D")}`
					: totalMinutes <= 60
						? "last " + totalMinutes + " min"
						: "last " + Math.round(totalMinutes / 60) + " hours"
			})`,
			dataIndex: "time_series",
			key: "sparkline",
			width: 300,
			render: (time_series: Array<{ timestamp: number; count: number }>) => (
				<SparklineChart
					time_series={time_series}
					isCustomRange={isCustomRange}
					search={search}
					windowMinutes={windowMinutes}
					globalHoverTimestamp={globalHoverTimestamp}
					onHoverChange={setGlobalHoverTimestamp}
				/>
			),
		},
	];

	const controls = (
		<Space size={4}>
			<Select
				value={selectValue}
				onChange={handleWindowChange}
				options={selectOptions}
				style={{ width: 200 }}
				suffixIcon={
					isCustomRange ? <CalendarOutlined /> : <ClockCircleOutlined />
				}
				onSelect={(value) => {
					// Always open modal when selecting custom range option, even if already selected
					if (value === -1) {
						// Set the current custom range from URL if it exists
						if (isCustomRange && search.startTime && search.endTime) {
							setCustomRange([dayjs(search.startTime), dayjs(search.endTime)]);
						}
						setCustomRangeModalVisible(true);
					}
				}}
			/>
			<Button
				type={autoRefresh ? "primary" : "default"}
				onClick={() => updateSearch({ autoRefresh: !autoRefresh })}
				icon={<ReloadOutlined spin={autoRefresh && isFetching} />}
			>
				{autoRefresh ? "Auto" : "Manual"}
			</Button>
			<Button
				icon={<ReloadOutlined />}
				onClick={() => refetch()}
				loading={isFetching}
			>
				Refresh
			</Button>
		</Space>
	);

	const pageActionsContainer = document.getElementById("page-actions");

	return (
		<div className="space-y-4">
			{pageActionsContainer && createPortal(controls, pageActionsContainer)}

			{ignored_paths.length > 0 && (
				<Alert
					message="Ignored Paths"
					description={ignored_paths.join(", ")}
					type="info"
					showIcon
					closable
				/>
			)}

			{paths.length > 0 ? (
				<Table
					columns={columns}
					dataSource={paths}
					rowKey={(record) => `${record.method}-${record.path}`}
					size="small"
					pagination={{
						pageSize: 20,
						showSizeChanger: true,
						pageSizeOptions: ["10", "20", "50", "100"],
						showTotal: (total, range) => (
							<span className="text-xs">
								{range[0]}-{range[1]} of {total} paths
							</span>
						),
					}}
					defaultSortOrder="descend"
					scroll={{ x: 600 }}
				/>
			) : (
				<Empty description="No path data available" />
			)}

			<div className="text-center">
				<Text type="secondary" className="text-xs">
					Step: 1 minute | Window:{" "}
					{isCustomRange && search.startTime && search.endTime
						? `${dayjs(search.startTime).format("MMM D, HH:mm")} - ${dayjs(search.endTime).format("MMM D, HH:mm")}`
						: `Rolling ${totalMinutes} minutes`}{" "}
					|{" "}
					{autoRefresh
						? "Auto-refresh: ON (updates every minute)"
						: "Auto-refresh: OFF"}
				</Text>
			</div>

			{/* Custom Range Modal */}
			<Modal
				title="Select Custom Date Range"
				open={customRangeModalVisible}
				onOk={handleCustomRangeOk}
				onCancel={() => setCustomRangeModalVisible(false)}
				okButtonProps={{ disabled: !customRange }}
			>
				<RangePicker
					showTime
					format="YYYY-MM-DD HH:mm"
					value={customRange}
					onChange={(values) =>
						setCustomRange(values as [dayjs.Dayjs, dayjs.Dayjs])
					}
					style={{ width: "100%" }}
					disabledDate={(current) => current && current.isAfter(dayjs())}
				/>
				{customRange && (
					<div style={{ marginTop: 10 }}>
						<Text type="secondary">
							Duration:{" "}
							{Math.round(customRange[1].diff(customRange[0], "minute"))}{" "}
							minutes (
							{Math.round(
								customRange[1].diff(customRange[0], "hour", true) * 10,
							) / 10}{" "}
							hours)
						</Text>
					</div>
				)}
			</Modal>
		</div>
	);
}
