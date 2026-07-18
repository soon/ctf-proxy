import { useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import {
	Button,
	Space,
	Typography,
	Tag,
	Table,
	Input,
	Card,
	App,
	Empty,
	Popconfirm,
	Spin,
	Dropdown,
} from "antd";
import {
	SaveOutlined,
	PlayCircleOutlined,
	RocketOutlined,
	DeleteOutlined,
	PlusOutlined,
	ArrowLeftOutlined,
	HistoryOutlined,
	DownOutlined,
} from "@ant-design/icons";
import Editor from "@monaco-editor/react";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
	analyzerListRulesApiAnalyzerRulesGetOptions,
	analyzerSaveRuleApiAnalyzerRulesNamePutMutation,
	analyzerDeleteRuleApiAnalyzerRulesNameDeleteMutation,
	analyzerPromoteRuleApiAnalyzerRulesNamePromotePostMutation,
	analyzerPreviewApiAnalyzerPreviewPostMutation,
	analyzerCreateBackfillApiAnalyzerBackfillPostMutation,
	getServiceByPortApiServicesPortGetOptions,
	getServiceRequestsApiServicesPortRequestsGetOptions,
	getTcpConnectionsApiServicesPortTcpConnectionsGetOptions,
} from "@/client/@tanstack/react-query.gen";
import { analyzerGetRuleApiAnalyzerRulesNameGet } from "@/client/sdk.gen";
import type { RuleInfoModel, PreviewMatchModel } from "@/client/types.gen";

const { Text } = Typography;

export const Route = createFileRoute("/service/$port/rules")({
	component: ServiceRules,
	staticData: { breadcrumb: "Rules", isWide: true },
});

function template(port: number): string {
	return `from ctf_proxy.analyzer.rule import Match, PatternRule


class MyRule(PatternRule):
    name = "my_rule"
    port = ${port}  # applies to this service only; remove to apply to all ports

    def match(self, ctx):
        if "TODO" in (ctx.path or ""):
            yield Match(tag="my_tag", meta=ctx.path)
`;
}

function ServiceRules() {
	const { port } = Route.useParams();
	const portNumber = Number.parseInt(port, 10);
	const navigate = useNavigate();
	const { message } = App.useApp();

	const [name, setName] = useState("");
	const [source, setSource] = useState("");
	const [status, setStatus] = useState<"draft" | "enabled">("draft");
	const [selectedIds, setSelectedIds] = useState<number[]>([]);
	const [matches, setMatches] = useState<PreviewMatchModel[]>([]);

	const { data: service } = useQuery({
		...getServiceByPortApiServicesPortGetOptions({
			path: { port: portNumber },
		}),
	});
	const isTcp = service?.type === "tcp";
	const sourceType = isTcp ? "tcp" : "http";

	const {
		data: rulesData,
		isLoading: rulesLoading,
		refetch: refetchRules,
	} = useQuery({
		...analyzerListRulesApiAnalyzerRulesGetOptions({
			query: { port: portNumber },
		}),
		refetchInterval: false,
	});
	const rules = rulesData?.rules ?? [];

	const { data: requestsData, isLoading: requestsLoading } = useQuery({
		...getServiceRequestsApiServicesPortRequestsGetOptions({
			path: { port: portNumber },
			query: { page: 1, page_size: 50 },
		}),
		enabled: !!service && !isTcp,
	});

	const { data: tcpData, isLoading: tcpLoading } = useQuery({
		...getTcpConnectionsApiServicesPortTcpConnectionsGetOptions({
			path: { port: portNumber },
			query: { page: 1, page_size: 50 },
		}),
		enabled: !!service && isTcp,
	});

	const entities = isTcp
		? (tcpData?.connections ?? [])
		: (requestsData?.requests ?? []);
	const entitiesLoading = isTcp ? tcpLoading : requestsLoading;

	const saveMutation = useMutation({
		...analyzerSaveRuleApiAnalyzerRulesNamePutMutation(),
		onSuccess: () => {
			message.success(`Saved draft "${name}"`);
			refetchRules();
		},
		onError: (error) => message.error(`Save failed: ${describeError(error)}`),
	});

	const deleteMutation = useMutation({
		...analyzerDeleteRuleApiAnalyzerRulesNameDeleteMutation(),
		onSuccess: () => {
			message.success("Rule deleted");
			resetEditor();
			refetchRules();
		},
		onError: (error) => message.error(`Delete failed: ${describeError(error)}`),
	});

	const promoteMutation = useMutation({
		...analyzerPromoteRuleApiAnalyzerRulesNamePromotePostMutation(),
		onSuccess: () => {
			message.success(`Promoted "${name}"`);
			setStatus("enabled");
			refetchRules();
		},
		onError: (error) =>
			message.error(`Promote failed: ${describeError(error)}`),
	});

	const backfillMutation = useMutation({
		...analyzerCreateBackfillApiAnalyzerBackfillPostMutation(),
		onSuccess: (job) =>
			message.success(`Backfill queued up to id ${job.target_id}`),
		onError: (error) =>
			message.error(`Backfill failed: ${describeError(error)}`),
	});

	const previewMutation = useMutation({
		...analyzerPreviewApiAnalyzerPreviewPostMutation(),
		onSuccess: (result) => {
			setMatches(result.matches);
			message.success(
				`${result.count} match(es) across ${result.scanned} scanned`,
			);
		},
		onError: (error) =>
			message.error(`Preview failed: ${describeError(error)}`),
	});

	function resetEditor() {
		setName("");
		setSource("");
		setStatus("draft");
		setMatches([]);
	}

	function newRule() {
		setName("");
		setSource(template(portNumber));
		setStatus("draft");
		setMatches([]);
	}

	async function loadRule(rule: RuleInfoModel) {
		const response = await analyzerGetRuleApiAnalyzerRulesNameGet({
			path: { name: rule.name },
			query: { status: rule.status },
		});
		if (response.data) {
			setName(response.data.name);
			setSource(response.data.source);
			setStatus(rule.status as "draft" | "enabled");
			setMatches([]);
		}
	}

	function save() {
		if (!name.trim()) {
			message.warning("Enter a rule name first");
			return;
		}
		saveMutation.mutate({ path: { name }, body: { source } });
	}

	function runBackfill(ports: number[] | null) {
		backfillMutation.mutate({ body: { ports } });
	}

	function runPreview() {
		if (!source.trim()) {
			message.warning("Nothing to preview - click New or open a rule");
			return;
		}
		const ids =
			selectedIds.length > 0 ? selectedIds : entities.map((e) => e.id);
		if (ids.length === 0) {
			message.warning("No entities in this service to preview against");
			return;
		}
		previewMutation.mutate({ body: { source, source_type: sourceType, ids } });
	}

	const matchedIds = new Set(matches.map((m) => m.ref_id));

	const ruleColumns = [
		{
			title: "Name",
			dataIndex: "name",
			key: "name",
			render: (value: string, rule: RuleInfoModel) => (
				<Button
					type="link"
					style={{ padding: 0 }}
					onClick={() => loadRule(rule)}
				>
					{value}
				</Button>
			),
		},
		{
			title: "Status",
			dataIndex: "status",
			key: "status",
			render: (value: string) => (
				<Tag color={value === "enabled" ? "green" : "gold"}>{value}</Tag>
			),
		},
		{
			title: "Port",
			dataIndex: "port",
			key: "port",
			render: (value: number | null) =>
				value == null ? <Text type="secondary">all</Text> : value,
		},
	];

	const entityColumns = isTcp
		? [
				{ title: "ID", dataIndex: "id", key: "id", width: 70 },
				{
					title: "Conn",
					dataIndex: "connection_id",
					key: "connection_id",
					width: 80,
				},
				{
					title: "Bytes In",
					dataIndex: "bytes_in",
					key: "bytes_in",
					width: 90,
				},
				{
					title: "Bytes Out",
					dataIndex: "bytes_out",
					key: "bytes_out",
					width: 90,
				},
				{
					title: "Match",
					key: "match",
					render: (_: unknown, row: { id: number }) =>
						matchTag(matchedIds, matches, row.id),
				},
			]
		: [
				{ title: "ID", dataIndex: "id", key: "id", width: 70 },
				{ title: "Method", dataIndex: "method", key: "method", width: 80 },
				{ title: "Path", dataIndex: "path", key: "path", ellipsis: true },
				{
					title: "Match",
					key: "match",
					render: (_: unknown, row: { id: number }) =>
						matchTag(matchedIds, matches, row.id),
				},
			];

	if (!service) {
		return (
			<div className="flex justify-center py-8">
				<Spin />
			</div>
		);
	}

	return (
		<div style={{ display: "flex", gap: 16, height: "calc(100vh - 160px)" }}>
			<Card
				size="small"
				title={
					<Space>
						<Button
							size="small"
							icon={<ArrowLeftOutlined />}
							onClick={() => navigate({ to: `/service/${port}` })}
						/>
						{service.name} rules
					</Space>
				}
				style={{ width: 320, display: "flex", flexDirection: "column" }}
				styles={{ body: { overflow: "auto", flex: 1 } }}
				extra={
					<Button
						size="small"
						type="primary"
						icon={<PlusOutlined />}
						onClick={newRule}
					>
						New
					</Button>
				}
			>
				<Table
					rowKey={(rule) => `${rule.status}:${rule.name}`}
					size="small"
					loading={rulesLoading}
					dataSource={rules}
					columns={ruleColumns}
					pagination={false}
					locale={{ emptyText: "No rules for this service yet" }}
				/>
			</Card>

			<div
				style={{
					flex: 1,
					display: "flex",
					flexDirection: "column",
					gap: 12,
					minWidth: 0,
				}}
			>
				<Space wrap>
					<Input
						placeholder="rule name (a-z, 0-9, _-)"
						value={name}
						onChange={(e) => setName(e.target.value)}
						style={{ width: 220 }}
						addonBefore={
							<Tag color={status === "enabled" ? "green" : "gold"}>
								{status}
							</Tag>
						}
					/>
					<Button
						icon={<SaveOutlined />}
						type="primary"
						loading={saveMutation.isPending}
						onClick={save}
					>
						Save draft
					</Button>
					<Popconfirm
						title="Promote this draft to an enabled rule?"
						onConfirm={() => promoteMutation.mutate({ path: { name } })}
						disabled={status !== "draft" || !name}
					>
						<Button
							icon={<RocketOutlined />}
							loading={promoteMutation.isPending}
							disabled={status !== "draft" || !name}
						>
							Promote
						</Button>
					</Popconfirm>
					<Dropdown.Button
						icon={<DownOutlined />}
						loading={backfillMutation.isPending}
						onClick={() => runBackfill([portNumber])}
						menu={{
							items: [{ key: "all", label: "Backfill on all ports" }],
							onClick: () => runBackfill(null),
						}}
					>
						<HistoryOutlined /> Backfill port {port}
					</Dropdown.Button>
					<Popconfirm
						title={`Delete ${status} rule "${name}"?`}
						onConfirm={() =>
							deleteMutation.mutate({ path: { name }, query: { status } })
						}
						disabled={!name}
					>
						<Button icon={<DeleteOutlined />} danger disabled={!name}>
							Delete
						</Button>
					</Popconfirm>
				</Space>

				<Editor
					height="40%"
					language="python"
					value={source}
					onChange={(value) => setSource(value ?? "")}
					options={{ minimap: { enabled: false }, fontSize: 13 }}
				/>

				<Card
					size="small"
					title={`Preview against ${service.name} ${isTcp ? "connections" : "requests"}`}
					styles={{ body: { padding: 12, overflow: "auto" } }}
					extra={
						<Space>
							<Text type="secondary">
								{selectedIds.length > 0
									? `${selectedIds.length} selected`
									: `all ${entities.length}`}
								{matches.length > 0 ? ` · ${matches.length} match(es)` : ""}
							</Text>
							<Button
								icon={<PlayCircleOutlined />}
								loading={previewMutation.isPending}
								onClick={runPreview}
							>
								Preview
							</Button>
						</Space>
					}
				>
					{entitiesLoading ? (
						<Spin />
					) : entities.length === 0 ? (
						<Empty description="No traffic recorded for this service yet" />
					) : (
						<Table
							rowKey="id"
							size="small"
							dataSource={entities}
							columns={entityColumns}
							pagination={false}
							scroll={{ y: 240 }}
							rowClassName={(row: { id: number }) =>
								matchedIds.has(row.id) ? "preview-match" : ""
							}
							rowSelection={{
								selectedRowKeys: selectedIds,
								onChange: (keys) => setSelectedIds(keys as number[]),
							}}
						/>
					)}
				</Card>
			</div>
		</div>
	);
}

function matchTag(
	matchedIds: Set<number>,
	matches: PreviewMatchModel[],
	id: number,
) {
	if (!matchedIds.has(id)) return null;
	const tags = matches.filter((m) => m.ref_id === id);
	return (
		<Space size={2} wrap>
			{tags.map((m) => (
				<Tag color="blue" key={`${m.rule}:${m.tag}`}>
					{m.tag}
				</Tag>
			))}
		</Space>
	);
}

function describeError(error: unknown): string {
	if (error && typeof error === "object" && "detail" in error) {
		const detail = (error as { detail?: unknown }).detail;
		if (typeof detail === "string") return detail;
	}
	return error instanceof Error ? error.message : "unknown error";
}
