import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
	getServicesApiServicesGetOptions,
	getAllRequestTimeStatsApiRequestTimeStatsGetOptions,
} from "@/client/@tanstack/react-query.gen";
import { SparklineChart } from "@/components/SparklineChart";
import { TimeWindowSelector } from "@/components/TimeWindowSelector";
import { Table, Card, Button, Empty, Spin, Typography, Space } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { useState } from "react";
import { createPortal } from "react-dom";

const { Title, Text } = Typography;

export const Route = createFileRoute("/stats/requests")({
	component: RequestsStats,
	staticData: {
		breadcrumb: "Request Stats",
	},
});

function RequestsStats() {
	const [windowMinutes, setWindowMinutes] = useState(60);
	const [hoverTimestamp, setHoverTimestamp] = useState<number | null>(null);

	// Get all services
	const { data: servicesData } = useQuery({
		...getServicesApiServicesGetOptions(),
		refetchInterval: 30000,
	});

	// Get request time stats for all services
	const {
		data: requestStats,
		isLoading,
		refetch,
	} = useQuery({
		...getAllRequestTimeStatsApiRequestTimeStatsGetOptions({
			query: { window_minutes: windowMinutes },
		}),
		refetchInterval: 30000,
	});

	// Group stats by port
	const statsByPort = new Map<number, any[]>();
	if (requestStats?.stats) {
		requestStats.stats.forEach((stat: any) => {
			if (!statsByPort.has(stat.port)) {
				statsByPort.set(stat.port, []);
			}
			statsByPort.get(stat.port)?.push(stat);
		});
	}

	// Prepare table data
	const tableData = servicesData?.services
		.filter((service) => service.type === "http")
		.map((service) => {
			const stats = statsByPort.get(service.port) || [];
			const totalRequests = stats.reduce((sum, s) => sum + s.count, 0);
			const blockedRequests = stats.reduce(
				(sum, s) => sum + s.blocked_count,
				0,
			);

			return {
				key: service.port,
				port: service.port,
				name: service.name,
				totalRequests,
				blockedRequests,
				timeSeries: stats.map((s) => ({
					timestamp: new Date(s.time).getTime(),
					count: s.count,
				})),
			};
		})
		.sort((a, b) => a.port - b.port);

	const columns = [
		{
			title: "Port",
			dataIndex: "port",
			key: "port",
			width: 80,
		},
		{
			title: "Service",
			dataIndex: "name",
			key: "name",
			width: 200,
			render: (name: string) => (
				<Text strong className="font-mono">
					{name}
				</Text>
			),
		},
		{
			title: "Total Requests",
			dataIndex: "totalRequests",
			key: "totalRequests",
			width: 120,
			sorter: (a: any, b: any) => a.totalRequests - b.totalRequests,
			render: (value: number) => value.toLocaleString(),
		},
		{
			title: "Blocked",
			dataIndex: "blockedRequests",
			key: "blockedRequests",
			width: 100,
			render: (value: number, record: any) => (
				<Text type={value > 0 ? "danger" : undefined}>
					{value} (
					{record.totalRequests > 0
						? ((value / record.totalRequests) * 100).toFixed(1)
						: 0}
					%)
				</Text>
			),
		},
		{
			title: "Activity",
			key: "activity",
			width: 300,
			render: (_: any, record: any) => (
				<SparklineChart
					time_series={record.timeSeries}
					windowMinutes={windowMinutes}
					globalHoverTimestamp={hoverTimestamp}
					onHoverChange={setHoverTimestamp}
				/>
			),
		},
	];

	const controls = (
		<Space>
			<TimeWindowSelector value={windowMinutes} onChange={setWindowMinutes} />
			<Button icon={<ReloadOutlined />} onClick={() => refetch()}>
				Refresh
			</Button>
		</Space>
	);

	const pageActionsContainer = document.getElementById("page-actions");

	if (isLoading) {
		return (
			<div className="flex justify-center items-center h-64">
				<Spin size="large" tip="Loading request statistics..." />
			</div>
		);
	}

	return (
		<div className="space-y-4">
			{pageActionsContainer && createPortal(controls, pageActionsContainer)}

			{tableData && tableData.length > 0 ? (
				<Table
					dataSource={tableData}
					columns={columns}
					pagination={false}
					size="small"
					scroll={{ x: 800 }}
				/>
			) : (
				<Card>
					<Empty description="No request data available for the selected time window" />
				</Card>
			)}
		</div>
	);
}
