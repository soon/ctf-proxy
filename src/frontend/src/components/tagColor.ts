const TAG_COLORS = [
	"magenta",
	"red",
	"volcano",
	"orange",
	"gold",
	"lime",
	"green",
	"cyan",
	"blue",
	"geekblue",
	"purple",
];

export function tagColor(tag: string): string {
	let hash = 0;
	for (let i = 0; i < tag.length; i++) {
		hash = (hash * 31 + tag.charCodeAt(i)) | 0;
	}
	return TAG_COLORS[Math.abs(hash) % TAG_COLORS.length];
}
