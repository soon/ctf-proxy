import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { getTcpConnectionStatsApiServicesPortTcpConnectionStatsGetOptions } from "@/client/@tanstack/react-query.gen";
import type { TcpConnectionStatsItem } from "@/client/types.gen";
import { Table, Spin, Empty, Typography, Select, Space, Button } from "antd";
import { ReloadOutlined, ClockCircleOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import { useState } from "react";
import { createPortal } from "react-dom";
import { SparklineChart } from "@/components/SparklineChart";

const { Text } = Typography;

export const Route = createFileRoute("/service/$port/tcp-stats")({
	component: TcpConnectionStats,
	staticData: {
		breadcrumb: "TCP Connection Patterns",
	},
});

function formatBytes(bytes: number): string {
	if (bytes < 1024) return `${bytes} B`;
	if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
	if (bytes < 1024 * 1024 * 1024)
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function TcpConnectionStats() {
	const { port } = Route.useParams();
	const portNumber = parseInt(port);
	const [windowMinutes, setWindowMinutes] = useState(60);
	const [globalHoverTimestamp, setGlobalHoverTimestamp] = useState<
		number | null
	>(null);

	const { data, isLoading, error, refetch } = useQuery({
		...getTcpConnectionStatsApiServicesPortTcpConnectionStatsGetOptions({
			path: { port: portNumber },
			query: { window_minutes: windowMinutes },
		}),
		refetchInterval: 30000,
	});

	if (isLoading) {
		return (
			<div className="flex justify-center items-center h-64">
				<Spin size="large" tip="Loading TCP connection statistics..." />
			</div>
		);
	}

	if (error || !data) {
		return (
			<Empty
				description={error?.message || "No TCP connection statistics available"}
			/>
		);
	}

	// Sort stats by total count
	const sortedStats = [...data.stats].sort((a, b) => b.count - a.count);

	const columns: ColumnsType<TcpConnectionStatsItem> = [
		{
			title: "Read Bytes",
			key: "read_range",
			width: 180,
			render: (_, record) => (
				<Text className="font-mono text-xs">
					{formatBytes(record.read_min)} - {formatBytes(record.read_max)}
				</Text>
			),
		},
		{
			title: "Write Bytes",
			key: "write_range",
			width: 180,
			render: (_, record) => (
				<Text className="font-mono text-xs">
					{formatBytes(record.write_min)} - {formatBytes(record.write_max)}
				</Text>
			),
		},
		{
			title: "Total",
			dataIndex: "count",
			key: "count",
			width: 80,
			sorter: (a, b) => a.count - b.count,
		},
		{
			title: "Activity",
			key: "sparkline",
			width: 300,
			render: (_, record) => (
				<SparklineChart
					time_series={record.time_series}
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
				value={windowMinutes}
				onChange={setWindowMinutes}
				style={{ width: 120 }}
				options={[
					{ value: 10, label: "10 min" },
					{ value: 30, label: "30 min" },
					{ value: 60, label: "1 hour" },
					{ value: 180, label: "3 hours" },
					{ value: 360, label: "6 hours" },
					{ value: 720, label: "12 hours" },
					{ value: 1440, label: "24 hours" },
				]}
				prefixCls="ant-select"
				suffixIcon={<ClockCircleOutlined />}
			/>
			<Button icon={<ReloadOutlined />} onClick={() => refetch()}>
				Refresh
			</Button>
		</Space>
	);

	const pageActionsContainer = document.getElementById("page-actions");

	return (
		<>
			{pageActionsContainer && createPortal(controls, pageActionsContainer)}
			<Table
				columns={columns}
				dataSource={sortedStats}
				rowKey={(record) =>
					`${record.read_min}-${record.read_max}-${record.write_min}-${record.write_max}`
				}
				size="small"
				pagination={{
					pageSize: 20,
					showSizeChanger: true,
					pageSizeOptions: ["10", "20", "50", "100"],
				}}
			/>
		</>
	);
}
