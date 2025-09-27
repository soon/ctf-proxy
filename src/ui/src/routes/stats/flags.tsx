import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
	getServicesApiServicesGetOptions,
	getAllFlagTimeStatsApiFlagTimeStatsGetOptions,
} from "@/client/@tanstack/react-query.gen";
import { SparklineChart } from "@/components/SparklineChart";
import { TimeWindowSelector } from "@/components/TimeWindowSelector";
import { Table, Card, Button, Empty, Spin, Typography, Space, Tag } from "antd";
import { ReloadOutlined, FlagOutlined } from "@ant-design/icons";
import { useState } from "react";
import { createPortal } from "react-dom";

const { Title, Text } = Typography;

export const Route = createFileRoute("/stats/flags")({
	component: FlagsStats,
	staticData: {
		breadcrumb: "Flag Stats",
	},
});

function FlagsStats() {
	const [windowMinutes, setWindowMinutes] = useState(60);
	const [hoverTimestamp, setHoverTimestamp] = useState<number | null>(null);

	// Get all services
	const { data: servicesData } = useQuery({
		...getServicesApiServicesGetOptions(),
		refetchInterval: 30000,
	});

	// Get flag time stats for all services
	const {
		data: flagStats,
		isLoading,
		refetch,
	} = useQuery({
		...getAllFlagTimeStatsApiFlagTimeStatsGetOptions({
			query: { window_minutes: windowMinutes },
		}),
		refetchInterval: 30000,
	});

	// Group stats by port
	const statsByPort = new Map<number, any[]>();
	if (flagStats?.stats) {
		flagStats.stats.forEach((stat: any) => {
			if (!statsByPort.has(stat.port)) {
				statsByPort.set(stat.port, []);
			}
			statsByPort.get(stat.port)?.push(stat);
		});
	}

	// Prepare table data
	const tableData = servicesData?.services
		.map((service) => {
			const stats = statsByPort.get(service.port) || [];
			const totalWritten = stats.reduce((sum, s) => sum + s.write_count, 0);
			const totalRead = stats.reduce((sum, s) => sum + s.read_count, 0);
			const totalFlags = totalWritten + totalRead;

			return {
				key: service.port,
				port: service.port,
				name: service.name,
				type: service.type,
				totalWritten,
				totalRead,
				totalFlags,
				timeSeries: stats.map((s) => ({
					timestamp: new Date(s.time).getTime(),
					count: s.total_count,
				})),
			};
		})
		.filter((item) => item.totalFlags > 0 || item.type === "http")
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
			render: (name: string, record: any) => (
				<Space>
					<Text strong className="font-mono">
						{name}
					</Text>
					<Tag color={record.type === "tcp" ? "blue" : "green"}>
						{record.type.toUpperCase()}
					</Tag>
				</Space>
			),
		},
		{
			title: "Written",
			dataIndex: "totalWritten",
			key: "totalWritten",
			width: 100,
			render: (value: number) => value.toLocaleString(),
		},
		{
			title: "Retrieved",
			dataIndex: "totalRead",
			key: "totalRead",
			width: 100,
			render: (value: number) => value.toLocaleString(),
		},
		{
			title: "Total Flags",
			dataIndex: "totalFlags",
			key: "totalFlags",
			width: 120,
			sorter: (a: any, b: any) => a.totalFlags - b.totalFlags,
			render: (value: number) => (
				<Space>
					<FlagOutlined />
					<Text strong>{value.toLocaleString()}</Text>
				</Space>
			),
		},
		{
			title: "Activity",
			key: "activity",
			width: 300,
			render: (_: any, record: any) =>
				record.timeSeries.length > 0 ? (
					<SparklineChart
						time_series={record.timeSeries}
						windowMinutes={windowMinutes}
						globalHoverTimestamp={hoverTimestamp}
						onHoverChange={setHoverTimestamp}
					/>
				) : (
					<Text type="secondary">No flag activity</Text>
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
				<Spin size="large" tip="Loading flag statistics..." />
			</div>
		);
	}

	// Calculate totals
	const totals = tableData?.reduce(
		(acc, item) => ({
			written: acc.written + item.totalWritten,
			read: acc.read + item.totalRead,
			total: acc.total + item.totalFlags,
		}),
		{ written: 0, read: 0, total: 0 },
	);

	return (
		<div className="space-y-4">
			{pageActionsContainer && createPortal(controls, pageActionsContainer)}

			{tableData && tableData.length > 0 ? (
				<Table
					dataSource={tableData}
					columns={columns}
					pagination={false}
					size="small"
					scroll={{ x: 900 }}
				/>
			) : (
				<Card>
					<Empty description="No flag data available for the selected time window" />
				</Card>
			)}
		</div>
	);
}
