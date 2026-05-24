export default function TypingIndicator() {
  return (
    <div className="animate-fade-up rounded-3xl border border-stone bg-surface p-5 shadow-card motion-reduce:animate-none sm:p-6">
      <div className="flex items-center gap-3">
        <span className="text-body font-medium text-slate">
          Enbek AI печатает
        </span>
        <span className="flex items-center gap-1.5">
          <Dot delay="0s" />
          <Dot delay="0.18s" />
          <Dot delay="0.36s" />
        </span>
      </div>
    </div>
  );
}

function Dot({ delay }: { delay: string }) {
  return (
    <span
      className="h-2 w-2 rounded-full bg-violet animate-typing-bounce motion-reduce:animate-none"
      style={{ animationDelay: delay }}
    />
  );
}
