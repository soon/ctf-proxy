import {
	analyzerCreateBackfillApiAnalyzerBackfillPostMutation,
	analyzerGetBackfillApiAnalyzerBackfillGetOptions,
	analyzerTagStatsApiAnalyzerTagStatsGetOptions,
	analyzerTagTimeStatsApiAnalyzerTagTimeStatsGetOptions,
} from "@/client/@tanstack/react-query.gen";
import type { TagStatItem } from "@/client/types.gen";
import { SparklineChart } from "@/components/SparklineChart";
import { ArrowLeftOutlined, RocketOutlined } from "@ant-design/icons";
import { useMutation, useQuery } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import {
	App,
	Button,
	Card,
	Empty,
	InputNumber,
	Select,
	Space,
	Spin,
	Switch,
	Table,
	Tag,
	Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useState } from "react";

const { Text } = Typography;

const WINDOW_OPTIONS = [
	{ label: "Last 1h", value: 60 },
	{ label: "Last 6h", value: 360 },
	{ label: "Last 24h", value: 1440 },
	{ label: "Last 3d", value: 4320 },
	{ label: "Last 7d", value: 10080 },
];

export const Route = createFileRoute("/service/$port/tags")({
	component: ServiceTags,
	staticData: { breadcrumb: "Tag stats" },
});

function ServiceTags() {
	const { port } = Route.useParams();
	const portNumber = Number.parseInt(port, 10);
	const navigate = useNavigate();
	const { message } = App.useApp();

	const [targetId, setTargetId] = useState<number | null>(null);
	const [allPorts, setAllPorts] = useState(false);
	const [windowMinutes, setWindowMinutes] = useState(1440);
	const [hoverTs, setHoverTs] = useState<number | null>(null);

	const {
		data: tagData,
		isLoading,
		refetch,
	} = useQuery({
		...analyzerTagStatsApiAnalyzerTagStatsGetOptions({
			query: { port: portNumber },
		}),
		refetchInterval: 10000,
	});

	const { data: timeData } = useQuery({
		...analyzerTagTimeStatsApiAnalyzerTagTimeStatsGetOptions({
			query: { port: portNumber, window_minutes: windowMinutes },
		}),
		refetchInterval: 10000,
	});

	const seriesByTag = new Map(
		(timeData?.tags ?? []).map((t) => [`${t.rule}:${t.tag}`, t.time_series]),
	);

	const { data: job, refetch: refetchJob } = useQuery({
		...analyzerGetBackfillApiAnalyzerBackfillGetOptions(),
		refetchInterval: 3000,
	});

	const backfillMutation = useMutation({
		...analyzerCreateBackfillApiAnalyzerBackfillPostMutation(),
		onSuccess: () => {
			message.success("Backfill scheduled");
			refetchJob();
			setTimeout(() => refetch(), 1000);
		},
		onError: () => message.error("Failed to schedule backfill"),
	});

	function runBackfill() {
		backfillMutation.mutate({
			body: {
				target_id: targetId ?? null,
				ports: allPorts ? null : [portNumber],
			},
		});
	}

	const tags: TagStatItem[] = tagData?.tags ?? [];
	const uniqueTags = Array.from(new Set(tags.map((t) => t.tag)));

	const columns: ColumnsType<TagStatItem> = [
		{
			title: "Rule",
			dataIndex: "rule",
			key: "rule",
			sorter: (a, b) => a.rule.localeCompare(b.rule),
			render: (rule: string) => <Text code>{rule}</Text>,
		},
		{
			title: "Tag",
			dataIndex: "tag",
			key: "tag",
			render: (tag: string) => <Tag color="purple">{tag}</Tag>,
		},
		{
			title: "HTTP",
			dataIndex: "http_count",
			key: "http_count",
			width: 100,
			sorter: (a, b) => (a.http_count ?? 0) - (b.http_count ?? 0),
		},
		{
			title: "TCP",
			dataIndex: "tcp_count",
			key: "tcp_count",
			width: 100,
			sorter: (a, b) => (a.tcp_count ?? 0) - (b.tcp_count ?? 0),
		},
		{
			title: "Total",
			dataIndex: "total",
			key: "total",
			width: 100,
			defaultSortOrder: "descend",
			sorter: (a, b) => (a.total ?? 0) - (b.total ?? 0),
		},
		{
			title: "Activity",
			key: "activity",
			width: 260,
			render: (_, record) => {
				const series = seriesByTag.get(`${record.rule}:${record.tag}`) ?? [];
				if (series.length === 0)
					return <Text type="secondary">—</Text>;
				return (
					<SparklineChart
						time_series={series}
						windowMinutes={windowMinutes}
						globalHoverTimestamp={hoverTs}
						onHoverChange={setHoverTs}
						anchorToNow
					/>
				);
			},
		},
	];

	return (
		<div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
			<Space>
				<Button
					size="small"
					icon={<ArrowLeftOutlined />}
					onClick={() => navigate({ to: `/service/${port}` })}
				/>
				<Typography.Title level={4} style={{ margin: 0 }}>
					Rule tags · port {port}
				</Typography.Title>
			</Space>

			<Card size="small" title={`Unique tags (${uniqueTags.length})`}>
				{uniqueTags.length === 0 ? (
					<Empty description="No rule matches yet — run a backfill below" />
				) : (
					<Space size={4} wrap>
						{uniqueTags.map((t) => (
							<Tag color="purple" key={t}>
								{t}
							</Tag>
						))}
					</Space>
				)}
			</Card>

			<Card size="small" title="Backfill">
				<Space wrap align="center">
					<Text type="secondary">Backfill up to id</Text>
					<InputNumber
						min={1}
						placeholder="latest"
						value={targetId ?? undefined}
						onChange={(v) => setTargetId(v ?? null)}
					/>
					<Text type="secondary">All ports</Text>
					<Switch checked={allPorts} onChange={setAllPorts} />
					<Button
						type="primary"
						icon={<RocketOutlined />}
						loading={backfillMutation.isPending}
						onClick={runBackfill}
					>
						Run backfill
					</Button>
					{job ? (
						<Text type="secondary">
							last job #{job.id}: <Tag>{job.status}</Tag>
							target {job.target_id} · http@{job.http_cursor} · tcp@
							{job.tcp_cursor}
						</Text>
					) : null}
				</Space>
			</Card>

			<Card
				size="small"
				title="Aggregated tag stats"
				extra={
					<Select
						size="small"
						value={windowMinutes}
						onChange={setWindowMinutes}
						options={WINDOW_OPTIONS}
						style={{ width: 120 }}
					/>
				}
			>
				{isLoading ? (
					<div className="flex justify-center py-8">
						<Spin />
					</div>
				) : (
					<Table
						rowKey={(r) => `${r.rule}:${r.tag}`}
						size="small"
						columns={columns}
						dataSource={tags}
						pagination={{ pageSize: 20, showSizeChanger: true }}
					/>
				)}
			</Card>
		</div>
	);
}
