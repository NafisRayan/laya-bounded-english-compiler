// verification_webhook -- admin approval callback for
// verification_documents (Developer Spec.md §8.7).
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

Deno.serve(async (req) => {
  const { document_id, status } = await req.json();
  if (!document_id || !status) {
    return new Response(
      JSON.stringify({ error: "document_id and status are required" }),
      { status: 400, headers: { "Content-Type": "application/json" } },
    );
  }

  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );

  const { error } = await supabase
    .from("verification_documents")
    .update({ status, reviewed_at: new Date().toISOString() })
    .eq("id", document_id);
  if (error) {
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }

  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
});
