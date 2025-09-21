import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { getTcpConnectionDetailApiTcpConnectionsConnectionIdGetOptions } from "@/client/@tanstack/react-query.gen";
import {
	Card,
	Descriptions,
	Table,
	Tag,
	Button,
	Space,
	Empty,
	Spin,
	Typography,
	Tabs,
	Radio,
	Tooltip,
} from "antd";
import {
	ArrowLeftOutlined,
	FlagOutlined,
	DownloadOutlined,
	ClockCircleOutlined,
	SwapOutlined,
	CopyOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import { useState } from "react";

const { Text, Paragraph } = Typography;

type DisplayMode = "utf8" | "ascii" | "hex";

export const Route = createFileRoute("/service/$port/tcp-connection/$id")({
	component: TcpConnectionDetail,
});

function formatBytes(bytes: number): string {
	if (bytes < 1024) return `${bytes} B`;
	if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
	if (bytes < 1024 * 1024 * 1024)
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function decodeBase64(base64: string, mode: DisplayMode): string {
	try {
		// Decode base64 to binary string
		const binaryString = atob(base64);
		const bytes = new Uint8Array(binaryString.length);
		for (let i = 0; i < binaryString.length; i++) {
			bytes[i] = binaryString.charCodeAt(i);
		}

		switch (mode) {
			case "hex":
				return Array.from(bytes)
					.map((b) => b.toString(16).padStart(2, "0"))
					.join(" ")
					.toUpperCase();

			case "ascii":
				return Array.from(bytes)
					.map((b) => {
						// Printable ASCII range (32-126)
						if (b >= 32 && b <= 126) {
							return String.fromCharCode(b);
						}
						// Common control characters
						if (b === 9) return "\\t"; // Tab
						if (b === 10) return "\\n"; // Line feed
						if (b === 13) return "\\r"; // Carriage return
						// Non-printable as hex
						return `\\x${b.toString(16).padStart(2, "0")}`;
					})
					.join("");

			case "utf8":
			default:
				// Use TextDecoder for proper UTF-8 decoding
				const decoder = new TextDecoder("utf-8", { fatal: false });
				return decoder.decode(bytes);
		}
	} catch (error) {
		console.error("Failed to decode base64:", error);
		return "<decoding error>";
	}
}

function TcpConnectionDetail() {
	const { port, id } = Route.useParams();
	const navigate = useNavigate();
	const [displayMode, setDisplayMode] = useState<DisplayMode>("utf8");

	const connectionId = parseInt(id);

	const {
		data: connection,
		isLoading,
		error,
	} = useQuery({
		...getTcpConnectionDetailApiTcpConnectionsConnectionIdGetOptions({
			path: { connection_id: connectionId },
		}),
		refetchInterval: 5000,
	});

	if (isLoading) {
		return (
			<div className="flex justify-center items-center h-64">
				<Spin size="large" tip="Loading TCP connection details..." />
			</div>
		);
	}

	if (error || !connection) {
		return (
			<div className="p-4">
				<Button
					icon={<ArrowLeftOutlined />}
					onClick={() => navigate({ to: `/service/${port}` })}
				>
					Back to Service
				</Button>
				<Card className="mt-4">
					<Empty description={error?.message || "Connection not found"} />
				</Card>
			</div>
		);
	}

	const eventColumns: ColumnsType<any> = [
		{
			title: "Time",
			dataIndex: "timestamp",
			key: "timestamp",
			width: 150,
			render: (timestamp: string) =>
				new Date(timestamp).toLocaleTimeString("en-GB", {
					hour: "2-digit",
					minute: "2-digit",
					second: "2-digit",
					fractionalSecondDigits: 3,
				}),
		},
		{
			title: "Type",
			dataIndex: "event_type",
			key: "event_type",
			width: 80,
			render: (type: string) => {
				const display =
					type === "read" ? "IN" : type === "write" ? "OUT" : "CLOSED";
				const color =
					type === "read" ? "blue" : type === "write" ? "green" : "default";
				return <Tag color={color}>{display}</Tag>;
			},
		},
		{
			title: "Size",
			dataIndex: "data_size",
			key: "data_size",
			width: 100,
			render: (size: number) => formatBytes(size),
		},
		{
			title: "Data",
			dataIndex: "data_bytes",
			key: "data_bytes",
			ellipsis: true,
			render: (dataBytes: string | null, record: any) => {
				if (!dataBytes) {
					if (record.event_type === "closed") {
						return <Text type="secondary">Connection closed</Text>;
					}
					return <Text type="secondary">No data</Text>;
				}

				const decodedData = decodeBase64(dataBytes, displayMode);

				return (
					<div className="relative group">
						<Paragraph
							copyable={{ text: decodedData }}
							className="mb-0 font-mono text-xs whitespace-pre-wrap break-all"
							style={{
								maxWidth: "800px",
								wordBreak: displayMode === "hex" ? "break-all" : "break-word",
							}}
						>
							{decodedData}
						</Paragraph>
					</div>
				);
			},
		},
		{
			title: "Flags",
			dataIndex: "flags",
			key: "flags",
			width: 100,
			render: (flags: string[]) =>
				flags && flags.length > 0 ? (
					<Space direction="vertical" size={2}>
						{flags.map((flag, idx) => (
							<Tag
								key={idx}
								icon={<FlagOutlined />}
								color="red"
								className="text-xs"
							>
								{flag}
							</Tag>
						))}
					</Space>
				) : null,
		},
		{
			title: "Status",
			key: "status",
			width: 120,
			render: (_, record: any) => (
				<Space size={2}>
					{record.truncated && (
						<Tag color="warning" className="text-xs">
							TRUNCATED
						</Tag>
					)}
					{record.end_stream && (
						<Tag color="default" className="text-xs">
							END
						</Tag>
					)}
				</Space>
			),
		},
	];

	return (
		<div className="space-y-4">
			<Descriptions bordered size="small" column={{ xs: 1, sm: 2, lg: 3 }}>
				<Descriptions.Item label="Connection ID">
					<Text strong>{connection.connection_id}</Text>
				</Descriptions.Item>
				<Descriptions.Item label="Timestamp">
					{new Date(connection.timestamp).toLocaleString()}
				</Descriptions.Item>
				<Descriptions.Item label="Port">
					<Text strong>{connection.port}</Text>
				</Descriptions.Item>
				<Descriptions.Item label="Bytes In">
					{formatBytes(connection.bytes_in)}
				</Descriptions.Item>
				<Descriptions.Item label="Bytes Out">
					{formatBytes(connection.bytes_out)}
				</Descriptions.Item>
				<Descriptions.Item label="Duration">
					{connection.duration_ms !== null
						? connection.duration_ms >= 1000
							? `${(connection.duration_ms / 1000).toFixed(2)}s`
							: connection.duration_ms >= 1
								? `${connection.duration_ms.toFixed(1)}ms`
								: `${(connection.duration_ms * 1000000).toFixed(0)}ns`
						: "Active"}
				</Descriptions.Item>
				<Descriptions.Item label="Total Flags">
					{connection.total_flags > 0 ? (
						<Tag icon={<FlagOutlined />} color="red">
							{connection.total_flags}
						</Tag>
					) : (
						<Text type="secondary">None</Text>
					)}
				</Descriptions.Item>
			</Descriptions>

			<Card
				title={`Events (${connection.events?.length || 0})`}
				extra={
					<Radio.Group
						value={displayMode}
						onChange={(e) => setDisplayMode(e.target.value)}
						size="small"
					>
						<Radio.Button value="utf8">UTF-8</Radio.Button>
						<Radio.Button value="ascii">ASCII</Radio.Button>
						<Radio.Button value="hex">HEX</Radio.Button>
					</Radio.Group>
				}
			>
				{connection.events && connection.events.length > 0 ? (
					<Table
						columns={eventColumns}
						dataSource={connection.events}
						rowKey="id"
						size="small"
						pagination={{
							pageSize: 50,
							showSizeChanger: true,
							pageSizeOptions: ["20", "50", "100", "200"],
						}}
						scroll={{ x: 800 }}
					/>
				) : (
					<Empty description="No events recorded" />
				)}
			</Card>
		</div>
	);
}
