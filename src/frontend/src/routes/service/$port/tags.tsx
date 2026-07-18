import { analyzerTagStatsApiAnalyzerTagStatsGetOptions } from "@/client/@tanstack/react-query.gen";
import type { TagStatItem } from "@/client/types.gen";
import { SparklineChart } from "@/components/SparklineChart";
import { tagColor } from "@/components/tagColor";
import { ArrowLeftOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import {
	Button,
	Card,
	Empty,
	Select,
	Space,
	Spin,
	Table,
	Tag,
	Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useState } from "react";
import { z } from "zod";

const { Text } = Typography;

const WINDOW_OPTIONS = [
	{ label: "Last 1h", value: 60 },
	{ label: "Last 6h", value: 360 },
	{ label: "Last 24h", value: 1440 },
	{ label: "Last 3d", value: 4320 },
	{ label: "Last 7d", value: 10080 },
];

const WINDOW_STORAGE_KEY = "tagStatsWindowMinutes";
const DEFAULT_WINDOW = 60;

function loadStoredWindow(): number {
	const raw = Number(localStorage.getItem(WINDOW_STORAGE_KEY));
	return WINDOW_OPTIONS.some((o) => o.value === raw) ? raw : DEFAULT_WINDOW;
}

export const Route = createFileRoute("/service/$port/tags")({
	component: ServiceTags,
	validateSearch: z.object({ window: z.number().optional() }),
	staticData: { breadcrumb: "Tag stats" },
});

function ServiceTags() {
	const { port } = Route.useParams();
	const portNumber = Number.parseInt(port, 10);
	const navigate = useNavigate();
	const search = Route.useSearch();

	const windowMinutes = search.window ?? loadStoredWindow();
	const setWindowMinutes = (value: number) => {
		localStorage.setItem(WINDOW_STORAGE_KEY, String(value));
		navigate({
			to: `/service/${port}/tags`,
			search: (prev) => ({ ...prev, window: value }),
			replace: true,
		});
	};

	const [hoverTs, setHoverTs] = useState<number | null>(null);

	const { data: tagData, isLoading } = useQuery({
		...analyzerTagStatsApiAnalyzerTagStatsGetOptions({
			query: { port: portNumber, window_minutes: windowMinutes },
		}),
		refetchInterval: 10000,
	});

	const openTag = (tag: string) => {
		navigate({
			to: `/service/${port}`,
			search: (prev) => ({ ...prev, filter_tag: tag }),
		});
	};

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
			render: (tag: string) => (
				<Tag
					color={tagColor(tag)}
					style={{ cursor: "pointer" }}
					onClick={() => openTag(tag)}
				>
					{tag}
				</Tag>
			),
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
				const series = record.time_series ?? [];
				if (series.length === 0) return <Text type="secondary">—</Text>;
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
					<Empty description="No rule matches yet" />
				) : (
					<Space size={4} wrap>
						{uniqueTags.map((t) => (
							<Tag
								color={tagColor(t)}
								key={t}
								style={{ cursor: "pointer" }}
								onClick={() => openTag(t)}
							>
								{t}
							</Tag>
						))}
					</Space>
				)}
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
