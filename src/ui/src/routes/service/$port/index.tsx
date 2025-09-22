import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
	getServiceByPortApiServicesPortGetOptions,
	getServiceRequestsApiServicesPortRequestsGetOptions,
	getTcpConnectionsApiServicesPortTcpConnectionsGetOptions,
} from "@/client/@tanstack/react-query.gen";
import {
	Card,
	Table,
	Tag,
	Button,
	Input,
	Row,
	Col,
	Statistic,
	Space,
	Empty,
	Spin,
	Modal,
	List,
	Typography,
} from "antd";
import {
	ReloadOutlined,
	FlagOutlined,
	ApiOutlined,
	AlertOutlined,
	LinkOutlined,
	FilterOutlined,
	ClearOutlined,
	LineChartOutlined,
	SearchOutlined,
	FileTextOutlined,
	WarningOutlined,
	CodeOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import { useState, useCallback } from "react";
import { createPortal } from "react-dom";

const { Search } = Input;
const { Text } = Typography;

export const Route = createFileRoute("/service/$port/")({
	component: ServiceDetail,
	staticData: {
		breadcrumb: "Service",
	},
});

function formatBytes(bytes: number): string {
	if (bytes < 1024) return `${bytes} B`;
	if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
	if (bytes < 1024 * 1024 * 1024)
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function ServiceDetail() {
	const { port } = Route.useParams();
	const portNumber = parseInt(port);
	const navigate = useNavigate();
	const [currentPage, setCurrentPage] = useState(1);
	const [pageSize, setPageSize] = useState(30);
	const [filters, setFilters] = useState<{
		filter_path?: string;
		filter_method?: string;
		filter_status?: number;
		filter_blocked?: boolean;
	}>({});
	const [searchValue, setSearchValue] = useState("");
	const [alertsModalVisible, setAlertsModalVisible] = useState(false);
	const [rawRequestModalVisible, setRawRequestModalVisible] = useState(false);
	const [selectedRequestId, setSelectedRequestId] = useState<number | null>(
		null,
	);
	const [rawRequestData, setRawRequestData] = useState<any>(null);
	const [loadingRawData, setLoadingRawData] = useState(false);

	const {
		data: service,
		isLoading: serviceLoading,
		refetch: refetchService,
	} = useQuery({
		...getServiceByPortApiServicesPortGetOptions({
			path: { port: portNumber },
		}),
		refetchInterval: 5000,
	});

	const isTcpService = service?.type === "tcp";

	const {
		data: requestsData,
		isLoading: requestsLoading,
		refetch: refetchRequests,
	} = useQuery({
		...getServiceRequestsApiServicesPortRequestsGetOptions({
			path: { port: portNumber },
			query: {
				page: currentPage,
				page_size: pageSize,
				...filters,
			},
		}),
		enabled: !isTcpService && !!service,
		refetchInterval: 5000,
	});

	// Fetch TCP connections for TCP services
	const {
		data: tcpConnectionsData,
		isLoading: tcpConnectionsLoading,
		refetch: refetchTcpConnections,
	} = useQuery({
		...getTcpConnectionsApiServicesPortTcpConnectionsGetOptions({
			path: { port: portNumber },
			query: {
				page: currentPage,
				page_size: pageSize,
			},
		}),
		enabled: isTcpService && !!service,
		refetchInterval: 5000,
	});

	const handleSearch = useCallback((value: string) => {
		const trimmed = value.trim();
		setCurrentPage(1); // Reset to first page on new search
		if (!trimmed) {
			setFilters({});
			return;
		}

		// Parse filter commands similar to CLI
		if (trimmed.startsWith("/")) {
			setFilters({ filter_path: trimmed });
		} else if (trimmed.match(/^[1-5]\d{2}$/)) {
			setFilters({ filter_status: parseInt(trimmed) });
		} else if (
			["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"].includes(
				trimmed.toUpperCase(),
			)
		) {
			setFilters({ filter_method: trimmed.toUpperCase() });
		} else if (trimmed.toLowerCase() === "blocked") {
			setFilters({ filter_blocked: true });
		} else {
			// Default to path contains
			setFilters({ filter_path: trimmed });
		}
	}, []);

	const clearFilters = () => {
		setFilters({});
		setSearchValue("");
		setCurrentPage(1);
	};

	const handlePageChange = (page: number, newPageSize?: number) => {
		setCurrentPage(page);
		if (newPageSize && newPageSize !== pageSize) {
			setPageSize(newPageSize);
		}
	};

	const httpColumns: ColumnsType<any> = [
		{
			title: "ID",
			dataIndex: "id",
			key: "id",
			width: 60,
		},
		{
			title: "Time",
			dataIndex: "timestamp",
			key: "timestamp",
			width: 80,
			render: (timestamp: string) =>
				new Date(timestamp).toLocaleTimeString("en-GB", {
					hour: "2-digit",
					minute: "2-digit",
					second: "2-digit",
				}),
		},
		{
			title: "Method",
			dataIndex: "method",
			key: "method",
			width: 70,
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
					className="text-xs"
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
				<span className="font-mono text-xs">{path}</span>
			),
		},
		{
			title: "Status",
			dataIndex: "status",
			key: "status",
			width: 60,
			render: (status: number | null) =>
				status ? (
					<Tag
						color={
							status >= 200 && status < 300
								? "success"
								: status >= 300 && status < 400
									? "processing"
									: status >= 400 && status < 500
										? "warning"
										: status >= 500
											? "error"
											: "default"
						}
						className="text-xs"
					>
						{status}
					</Tag>
				) : (
					<span className="text-gray-400 text-xs">N/A</span>
				),
		},
		{
			title: "Flags",
			key: "flags",
			width: 100,
			render: (_, record: any) => {
				if (!record.request_flags && !record.response_flags) return null;
				return (
					<Space size={2}>
						{record.request_flags > 0 && (
							<Tag icon={<FlagOutlined />} color="blue" className="text-xs">
								{record.request_flags > 1 && `${record.request_flags} `}REQ
							</Tag>
						)}
						{record.response_flags > 0 && (
							<Tag icon={<FlagOutlined />} color="red" className="text-xs">
								{record.response_flags > 1 && `${record.response_flags} `}RESP
							</Tag>
						)}
					</Space>
				);
			},
		},
		{
			title: "Links",
			key: "links",
			width: 80,
			render: (_, record: any) => {
				const inCount = record.incoming_links || 0;
				const outCount = record.outgoing_links || 0;

				if (inCount === 0 && outCount === 0) return null;

				return (
					<svg
						width="60"
						height="20"
						viewBox="0 0 60 20"
						className="inline-block"
					>
						{inCount > 0 && outCount === 0 && (
							// Last request: arrow pointing at circle (red - terminal)
							<>
								<line
									x1="15"
									y1="10"
									x2="40"
									y2="10"
									stroke="#ef4444"
									strokeWidth="2"
								/>
								<polygon points="40,6 40,14 45,10" fill="#ef4444" />
								<circle cx="48" cy="10" r="3" fill="#ef4444" />
								{inCount > 1 && (
									<text
										x="5"
										y="14"
										fontSize="10"
										fill="#ef4444"
										fontWeight="bold"
									>
										{inCount}
									</text>
								)}
							</>
						)}
						{inCount === 0 && outCount > 0 && (
							// First request: circle with arrow coming out (green - starting)
							<>
								<circle cx="12" cy="10" r="3" fill="#10b981" />
								<line
									x1="15"
									y1="10"
									x2="40"
									y2="10"
									stroke="#10b981"
									strokeWidth="2"
								/>
								<polygon points="40,6 40,14 45,10" fill="#10b981" />
								{outCount > 1 && (
									<text
										x="50"
										y="14"
										fontSize="10"
										fill="#10b981"
										fontWeight="bold"
									>
										{outCount}
									</text>
								)}
							</>
						)}
						{inCount > 0 && outCount > 0 && (
							// Middle request: two circles connected (blue - intermediate)
							<>
								<circle cx="15" cy="10" r="3" fill="#3b82f6" />
								<line
									x1="18"
									y1="10"
									x2="42"
									y2="10"
									stroke="#3b82f6"
									strokeWidth="2"
								/>
								<circle cx="45" cy="10" r="3" fill="#3b82f6" />
								{inCount > 1 && (
									<text
										x="5"
										y="5"
										fontSize="10"
										fill="#3b82f6"
										fontWeight="bold"
									>
										{inCount}
									</text>
								)}
								{outCount > 1 && (
									<text
										x="50"
										y="5"
										fontSize="10"
										fill="#3b82f6"
										fontWeight="bold"
									>
										{outCount}
									</text>
								)}
							</>
						)}
					</svg>
				);
			},
		},
		{
			title: "Blocked",
			key: "blocked",
			width: 70,
			render: (_, record: any) =>
				record.is_blocked ? (
					<Tag color="error" className="text-xs">
						BLOCKED
					</Tag>
				) : null,
		},
		{
			title: "Raw",
			key: "actions",
			width: 60,
			render: (_, record: any) => (
				<Button
					size="small"
					icon={<CodeOutlined />}
					onClick={async (e) => {
						e.stopPropagation();
						setSelectedRequestId(record.id);
						setLoadingRawData(true);
						setRawRequestModalVisible(true);

						try {
							const apiUrl =
								localStorage.getItem("ctf-proxy-api-url") ||
								"http://localhost:48955";
							const response = await fetch(
								`${apiUrl}/api/requests/${record.id}/raw`,
							);
							if (response.ok) {
								const data = await response.json();
								setRawRequestData(data);
							} else {
								setRawRequestData({ error: "Failed to load raw data" });
							}
						} catch (error) {
							setRawRequestData({ error: String(error) });
						} finally {
							setLoadingRawData(false);
						}
					}}
				/>
			),
		},
	];

	// TCP Connections columns
	const tcpColumns: ColumnsType<any> = [
		{
			title: "ID",
			dataIndex: "id",
			key: "id",
			width: 60,
		},
		{
			title: "Conn ID",
			dataIndex: "connection_id",
			key: "connection_id",
			width: 80,
			render: (id: number) => <span className="font-mono text-xs">{id}</span>,
		},
		{
			title: "Time",
			dataIndex: "timestamp",
			key: "timestamp",
			width: 80,
			render: (timestamp: string) =>
				new Date(timestamp).toLocaleTimeString("en-GB", {
					hour: "2-digit",
					minute: "2-digit",
					second: "2-digit",
				}),
		},
		{
			title: "Bytes In",
			dataIndex: "bytes_in",
			key: "bytes_in",
			width: 90,
			render: (bytes: number) => {
				if (bytes < 1024) return `${bytes} B`;
				if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
				return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
			},
		},
		{
			title: "Bytes Out",
			dataIndex: "bytes_out",
			key: "bytes_out",
			width: 90,
			render: (bytes: number) => {
				if (bytes < 1024) return `${bytes} B`;
				if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
				return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
			},
		},
		{
			title: "Duration",
			dataIndex: "duration_ms",
			key: "duration_ms",
			width: 80,
			render: (ms: number | null) =>
				ms !== null ? (
					<span className="text-xs">
						{ms >= 1000
							? `${(ms / 1000).toFixed(2)}s`
							: ms >= 1
								? `${ms.toFixed(1)}ms`
								: `${(ms * 1000000).toFixed(0)}ns`}
					</span>
				) : (
					<span className="text-gray-400 text-xs">Active</span>
				),
		},
		{
			title: "Flags In",
			dataIndex: "flags_in",
			key: "flags_in",
			width: 80,
			render: (count: number) =>
				count > 0 ? (
					<Tag icon={<FlagOutlined />} color="blue" className="text-xs">
						IN: {count}
					</Tag>
				) : null,
		},
		{
			title: "Flags Out",
			dataIndex: "flags_out",
			key: "flags_out",
			width: 85,
			render: (count: number) =>
				count > 0 ? (
					<Tag icon={<FlagOutlined />} color="red" className="text-xs">
						OUT: {count}
					</Tag>
				) : null,
		},
		{
			title: "Blocked",
			dataIndex: "is_blocked",
			key: "is_blocked",
			width: 70,
			render: (blocked: boolean) =>
				blocked ? (
					<Tag color="error" className="text-xs">
						BLOCKED
					</Tag>
				) : null,
		},
	];

	if (serviceLoading || !service) {
		return (
			<div className="flex justify-center items-center h-64">
				<Spin size="large" tip="Loading service details..." />
			</div>
		);
	}

	const shortName = service.name.substring(0, 4).toUpperCase();

	const controls = (
		<Space size={4}>
			<Search
				placeholder="Filter: /path, 404, GET, blocked"
				allowClear
				enterButton={<FilterOutlined />}
				style={{ width: 250 }}
				value={searchValue}
				onChange={(e) => setSearchValue(e.target.value)}
				onSearch={handleSearch}
			/>
			{Object.keys(filters).length > 0 && (
				<Button icon={<ClearOutlined />} onClick={clearFilters}>
					Clear
				</Button>
			)}
			{isTcpService ? (
				<Button
					icon={<LineChartOutlined />}
					onClick={() => navigate({ to: `/service/${port}/tcp-stats` })}
				>
					TCP Stats
				</Button>
			) : (
				<>
					<Button
						icon={<LineChartOutlined />}
						onClick={() => navigate({ to: `/service/${port}/paths` })}
					>
						Paths
					</Button>
					<Button
						icon={<SearchOutlined />}
						onClick={() => navigate({ to: `/service/${port}/queries` })}
					>
						Queries
					</Button>
					<Button
						icon={<FileTextOutlined />}
						onClick={() => navigate({ to: `/service/${port}/headers` })}
					>
						Headers
					</Button>
				</>
			)}
			<Button
				icon={<ReloadOutlined />}
				onClick={() => {
					refetchService();
					if (isTcpService) {
						refetchTcpConnections();
					} else {
						refetchRequests();
					}
				}}
			>
				Refresh
			</Button>
		</Space>
	);

	const pageActionsContainer = document.getElementById("page-actions");

	return (
		<div className="space-y-2">
			{pageActionsContainer && createPortal(controls, pageActionsContainer)}
			{/* Stats Overview - More compact */}
			<Row gutter={[8, 8]}>
				<Col xs={12} sm={6}>
					<Card
						size="small"
						bodyStyle={{ padding: "8px", cursor: "pointer" }}
						className="hover:shadow-md transition-shadow"
					>
						<Statistic
							title={
								<span className="text-xs">
									{isTcpService ? "Connections" : "Requests"}
								</span>
							}
							value={
								isTcpService
									? service.stats.tcp_stats?.total_connections || 0
									: service.stats.total_requests
							}
							prefix={<ApiOutlined className="text-xs" />}
							valueStyle={{ fontSize: 14 }}
						/>
					</Card>
				</Col>
				<Col xs={12} sm={6}>
					<Card size="small" bodyStyle={{ padding: "8px" }}>
						{isTcpService ? (
							<Statistic
								title={<span className="text-xs">Bytes In/Out</span>}
								value={`${formatBytes(service.stats.tcp_stats?.total_bytes_in || 0)}/${formatBytes(service.stats.tcp_stats?.total_bytes_out || 0)}`}
								valueStyle={{ fontSize: 14 }}
							/>
						) : (
							<>
								<Statistic
									title={<span className="text-xs">Flags</span>}
									value={`${service.stats.flags_written}/${service.stats.flags_retrieved}`}
									prefix={<FlagOutlined className="text-xs" />}
									valueStyle={{ fontSize: 14 }}
								/>
								{service.stats.flags_blocked > 0 && (
									<div className="text-xs text-red-500">
										{service.stats.flags_blocked} blocked
									</div>
								)}
							</>
						)}
					</Card>
				</Col>
				<Col xs={12} sm={6}>
					<Card
						size="small"
						bodyStyle={{ padding: "8px", cursor: "pointer" }}
						className="hover:shadow-md transition-shadow"
						onClick={() => setAlertsModalVisible(true)}
					>
						<Statistic
							title={<span className="text-xs">Alerts</span>}
							value={service.stats.alerts_count}
							prefix={<AlertOutlined className="text-xs" />}
							valueStyle={{
								fontSize: 14,
								color: service.stats.alerts_count > 0 ? "#cf1322" : undefined,
							}}
						/>
					</Card>
				</Col>
				<Col xs={12} sm={6}>
					<Card
						size="small"
						bodyStyle={{ padding: "8px", cursor: "pointer" }}
						className="hover:shadow-md transition-shadow"
						onClick={() => navigate({ to: `/service/${port}/paths` })}
					>
						<Statistic
							title={<span className="text-xs">Paths</span>}
							value={service.stats.unique_paths}
							prefix={<LinkOutlined className="text-xs" />}
							valueStyle={{ fontSize: 14 }}
						/>
					</Card>
				</Col>
			</Row>

			{/* Requests Table for HTTP services or TCP Connections Table for TCP services */}
			{isTcpService ? (
				// TCP Connections Table
				tcpConnectionsLoading ? (
					<div className="flex justify-center py-4">
						<Spin />
					</div>
				) : tcpConnectionsData?.connections?.length === 0 ? (
					<Empty description="No TCP connections found" />
				) : (
					<Table
						columns={tcpColumns}
						dataSource={tcpConnectionsData?.connections}
						rowKey="id"
						size="small"
						pagination={{
							current: currentPage,
							pageSize: pageSize,
							total: tcpConnectionsData?.total || 0,
							showSizeChanger: true,
							pageSizeOptions: ["10", "20", "30", "50", "100"],
							onChange: handlePageChange,
							showTotal: (total, range) => (
								<span className="text-xs">
									{range[0]}-{range[1]} of {total} connections
								</span>
							),
						}}
						scroll={{ x: 700 }}
						rowClassName="hover:bg-gray-50 cursor-pointer"
						onRow={(record) => ({
							onClick: () =>
								navigate({
									to: `/service/${port}/tcp-connection/${record.id}`,
								}),
						})}
					/>
				)
			) : // HTTP Requests Table
			requestsLoading ? (
				<div className="flex justify-center py-4">
					<Spin />
				</div>
			) : requestsData?.requests?.length === 0 ? (
				<Empty description="No requests found" />
			) : (
				<Table
					columns={httpColumns}
					dataSource={requestsData?.requests}
					rowKey="id"
					size="small"
					pagination={{
						current: currentPage,
						pageSize: pageSize,
						total: requestsData?.total || 0,
						showSizeChanger: true,
						pageSizeOptions: ["10", "20", "30", "50", "100"],
						onChange: handlePageChange,
						showTotal: (total, range) => (
							<span className="text-xs">
								{range[0]}-{range[1]} of {total} requests
							</span>
						),
					}}
					scroll={{ x: 700 }}
					rowClassName="hover:bg-gray-50 cursor-pointer"
					onRow={(record) => ({
						onClick: () =>
							navigate({ to: `/service/${port}/request/${record.id}` }),
					})}
				/>
			)}

			{/* Alerts Modal */}
			<Modal
				title={
					<Space>
						<WarningOutlined style={{ color: "#cf1322" }} />
						<span>Recent Alerts</span>
					</Space>
				}
				open={alertsModalVisible}
				onCancel={() => setAlertsModalVisible(false)}
				footer={[
					<Button key="close" onClick={() => setAlertsModalVisible(false)}>
						Close
					</Button>,
				]}
				width={800}
			>
				{service?.stats.recent_alerts &&
				service.stats.recent_alerts.length > 0 ? (
					<List
						dataSource={service.stats.recent_alerts}
						renderItem={(alert: [string, any]) => (
							<List.Item>
								<Space direction="vertical" style={{ width: "100%" }}>
									<Text strong>{alert[0]}</Text>
									{typeof alert[1] === "object" ? (
										<pre className="text-xs bg-gray-100 p-2 rounded overflow-x-auto">
											{JSON.stringify(alert[1], null, 2)}
										</pre>
									) : (
										<Text className="text-sm">{String(alert[1])}</Text>
									)}
								</Space>
							</List.Item>
						)}
					/>
				) : (
					<Empty description="No alerts available" />
				)}
			</Modal>

			{/* Raw Request Modal */}
			<Modal
				title={
					<Space>
						<CodeOutlined />
						<span>Raw Request Data (ID: {selectedRequestId})</span>
					</Space>
				}
				open={rawRequestModalVisible}
				onCancel={() => {
					setRawRequestModalVisible(false);
					setRawRequestData(null);
				}}
				footer={[
					<Button
						key="close"
						onClick={() => {
							setRawRequestModalVisible(false);
							setRawRequestData(null);
						}}
					>
						Close
					</Button>,
				]}
				width={900}
			>
				{loadingRawData ? (
					<div className="flex justify-center py-8">
						<Spin tip="Loading raw data..." />
					</div>
				) : rawRequestData ? (
					rawRequestData.error ? (
						<Text type="danger">{rawRequestData.error}</Text>
					) : (
						<pre className="bg-gray-900 text-green-400 p-4 rounded-lg overflow-auto max-h-[500px] text-xs font-mono">
							{JSON.stringify(rawRequestData, null, 2)}
						</pre>
					)
				) : (
					<Empty description="No data available" />
				)}
			</Modal>
		</div>
	);
}
