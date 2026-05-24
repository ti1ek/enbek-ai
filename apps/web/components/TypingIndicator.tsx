export default function TypingIndicator() {
  return (
    <div className="flex items-center gap-2.5 animate-fade-up motion-reduce:animate-none">
      <span className="text-[14px] text-dusty">enbek ai печатает</span>
      <span className="flex items-center gap-1">
        <Dot delay="0s" />
        <Dot delay="0.18s" />
        <Dot delay="0.36s" />
      </span>
    </div>
  );
}

function Dot({ delay }: { delay: string }) {
  return (
    <span
      className="h-1.5 w-1.5 rounded-full bg-terra animate-typing-bounce motion-reduce:animate-none"
      style={{ animationDelay: delay }}
    />
  );
}
