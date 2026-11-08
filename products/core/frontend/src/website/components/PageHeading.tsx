/** The page's single <h1> for subpages whose body is a landing organ (organs head their sections with h2). */
export function PageHeading({ children }: { children: string }) {
  return (
    <div className="mx-auto w-full max-w-6xl px-4 pt-10 sm:px-6">
      <h1 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">{children}</h1>
    </div>
  );
}
